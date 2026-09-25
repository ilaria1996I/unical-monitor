"""Monitor UniCal: no credentials, response bodies or exception URLs in logs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

URL = 'https://www.unical.it/didattica/offerta-formativa/formazione-insegnanti/corsi-per-il-sostegno/sostegno-202526/'
SELECTOR = '.main-body > .py-5 > .container > .row > .col-lg-8'


class MonitorError(Exception):
    pass


def normalize(value):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFC', value).replace('\u200b', '')).strip()


def canonical_link(href):
    parts = urlsplit(urljoin(URL, href))
    if parts.scheme not in ('http', 'https'):
        return None
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.lower().startswith('utm_') and k.lower() not in ('fbclid', 'gclid')]
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path, urlencode(sorted(query)), ''))


def extract(html):
    soup = BeautifulSoup(html, 'html.parser')
    roots = soup.select(SELECTOR)
    if len(roots) != 1:
        raise MonitorError('Struttura UniCal inattesa: stato non aggiornato.')
    root = roots[0]
    for element in root.select('script, style, noscript, nav, footer, .breadcrumb, .it-cookie-banner, .it-cookie-modal'):
        element.decompose()
    # Keep collapsed accordion bodies: they contain the actual notices.
    text = normalize(root.get_text(' ', strip=True))
    if len(text) < 300 or 'sostegno' not in text.lower() or '2025' not in text:
        raise MonitorError('Contenuto UniCal incompleto: stato non aggiornato.')
    links = sorted({link for a in root.select('a[href]')
                    if not a['href'].strip().startswith('#')
                    if (link := canonical_link(a['href']))})
    return {'text': text, 'links': links}


def fingerprint(content):
    return hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def fetch_page():
    for attempt in range(3):
        try:
            req = Request(URL, headers={'User-Agent': 'UniCalMonitor/1.0', 'Accept-Language': 'it', 'Cache-Control': 'no-cache'})
            with urlopen(req, timeout=30) as response:
                if response.status != 200 or response.headers.get_content_type() != 'text/html':
                    raise ValueError()
                final = urlsplit(response.url)
                if final.hostname != 'www.unical.it' or final.path.rstrip('/') != urlsplit(URL).path.rstrip('/'):
                    raise ValueError()
                data = response.read(5_000_001)
                if len(data) > 5_000_000:
                    raise ValueError()
                return data.decode(response.headers.get_content_charset() or 'utf-8')
        except Exception:
            if attempt < 2:
                time.sleep(3 * (attempt + 1))
    raise MonitorError('Download UniCal fallito dopo tre tentativi.')


def send_telegram(message):
    token = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
    chat = os.environ.get('TELEGRAM_CHAT_ID', '').strip()
    if not token or not chat:
        raise MonitorError('Configurare entrambi i GitHub Secrets Telegram.')
    # Never print request URL, payload, response or raw exceptions (they contain secrets).
    try:
        body = json.dumps({'chat_id': chat, 'text': message,
                           'link_preview_options': {'is_disabled': True}}).encode()
        req = Request('https://api.telegram.org/bot' + token + '/sendMessage', data=body,
                      headers={'Content-Type': 'application/json'}, method='POST')
        with urlopen(req, timeout=30) as response:
            result = json.loads(response.read(100_000))
        if result.get('ok') is not True:
            raise ValueError()
    except Exception:
        raise MonitorError('Invio Telegram non confermato; stato precedente conservato.') from None


def load_state(path):
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text(encoding='utf-8'))
        if state['version'] != 1 or fingerprint(state['content']) != state['hash']:
            raise ValueError()
        datetime.fromisoformat(state['saved_at'])
        return state
    except Exception:
        raise MonitorError('Stato salvato non valido; ripristinarlo dalla cronologia Git.') from None


def run(path, test_message=False, fetch=fetch_page, send=send_telegram, confirm_delay=10):
    previous = load_state(path)
    content = extract(fetch())
    digest = fingerprint(content)
    changed = previous is not None and previous['hash'] != digest
    if changed:
        time.sleep(confirm_delay)
        if fingerprint(extract(fetch())) != digest:
            raise MonitorError('Pagina variabile tra due letture: riprova alla prossima esecuzione.')
    if previous is None:
        send('UniCal TFA Sostegno: monitor avviato. Prima lettura acquisita.\n' + URL)
    elif changed:
        added = len(set(content['links']) - set(previous['content']['links']))
        removed = len(set(previous['content']['links']) - set(content['links']))
        send('UniCal TFA Sostegno: contenuto della pagina modificato.\n'
             f'Link aggiunti: {added}; rimossi: {removed}.\nRiferimento: {digest[:12]}\n' + URL)
    elif test_message:
        send('UniCal TFA Sostegno: test riuscito. Pagina leggibile, nessuna modifica rilevata.\n' + URL)
    now = datetime.now(timezone.utc)
    # A monthly state refresh also gives scheduled public repositories activity.
    refresh = previous is None or (now - datetime.fromisoformat(previous['saved_at'])).days >= 30
    if changed or refresh:
        state = {'version': 1, 'saved_at': now.isoformat(), 'hash': digest, 'content': content}
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        temp.replace(path)
    print('Controllo completato: ' + ('inizializzato.' if previous is None else 'modifica notificata.' if changed else 'nessuna modifica.'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state', type=Path, default=Path('.state/state.json'))
    parser.add_argument('--test-message', action='store_true')
    parser.add_argument('--inspect-html', type=Path, help='Solo analisi locale, senza Telegram o salvataggio stato')
    args = parser.parse_args()
    try:
        if args.inspect_html:
            content = extract(args.inspect_html.read_text(encoding='utf-8'))
            print(f"Analisi riuscita: {len(content['text'])} caratteri, {len(content['links'])} link; hash {fingerprint(content)}")
        else:
            run(args.state, args.test_message)
    except MonitorError as error:
        print(str(error), file=sys.stderr)
        return 1
    except Exception:
        print('Errore inatteso: controllo interrotto senza esporre dati riservati.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
