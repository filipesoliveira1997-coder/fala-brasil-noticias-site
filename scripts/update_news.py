#!/usr/bin/env python3
"""Atualiza o catálogo do Fala Brasil Notícias a partir de feeds RSS públicos."""
import os, re, json, hashlib, html, time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlencode
import requests
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "news.json"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
MAX_PER_CATEGORY = 5
MAX_TOTAL = 60
UA = "FalaBrasilNoticiasBot/1.0 (+https://filipesoliveira1997-coder.github.io/fala-brasil-noticias-site/)"

CATEGORIES = [
    ("Brasil", "Brasil notícias", ""),
    ("Mundo", "notícias internacionais mundo", "blue"),
    ("Polícia", "segurança pública polícia Brasil", "red"),
    ("Economia", "economia Brasil negócios mercado", "gold"),
    ("Tecnologia", "tecnologia inovação ciência digital", "purple"),
    ("Esportes", "esportes futebol Brasil", "teal"),
    ("Entretenimento", "entretenimento cultura música cinema Brasil", "purple"),
    ("Saúde e bem-estar", "saúde ciência bem estar Brasil", "red"),
]


def clean_text(value):
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def parse_date(value):
    if not value:
        return datetime.now(timezone.utc)
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def google_news_url(query):
    params = {"q": query, "hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"}
    return "https://news.google.com/rss/search?" + urlencode(params)


def get_image(item):
    for el in item.iter():
        tag = el.tag.lower()
        if tag.endswith("thumbnail") or tag.endswith("content") or tag.endswith("enclosure"):
            url = el.attrib.get("url", "")
            if url.startswith("https://") or url.startswith("http://"):
                return url
    return ""


def fetch_category(category, query, tone):
    url = google_news_url(query)
    response = requests.get(url, headers={"User-Agent": UA}, timeout=25)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    channel = root.find("channel")
    found = []
    if channel is None:
        return found
    for item in channel.findall("item"):
        title = clean_text(item.findtext("title", ""))
        link = (item.findtext("link", "") or "").strip()
        desc = clean_text(item.findtext("description", ""))
        if not title or not link:
            continue
        source_el = item.find("source")
        source = clean_text(source_el.text if source_el is not None else "") or "Fonte identificada no Google Notícias"
        published = parse_date(item.findtext("pubDate", ""))
        # Só conteúdo recente: janela de 72 horas para reduzir notícias velhas.
        if (datetime.now(timezone.utc) - published).total_seconds() > 72 * 3600:
            continue
        key = hashlib.sha256(link.encode("utf-8")).hexdigest()[:14]
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:55] or "noticia"
        found.append({
            "id": f"{slug}-{key}", "category": category, "title": title,
            "snippet": desc[:900], "source": source, "url": link,
            "published": published.isoformat(), "image": get_image(item), "tone": tone
        })
    return found[:MAX_PER_CATEGORY]


def summarize_with_ai(items):
    if not OPENAI_API_KEY or not items:
        return {}
    payload = [{"id": x["id"], "title": x["title"], "source": x["source"], "snippet": x["snippet"]} for x in items]
    system = (
        "Você é editor de um portal jornalístico brasileiro. Escreva em português do Brasil. "
        "Resuma somente o que está explicitamente sustentado pelo título e pelo trecho fornecidos. "
        "Não invente fatos, datas, números, citações, causas, consequências ou declarações. "
        "Se o trecho for insuficiente, faça um resumo cauteloso que diga apenas o tema indicado no título. "
        "Não copie frases longas do trecho. Não dê opinião. Retorne JSON válido com a chave items; "
        "cada item deve ter id, dek (uma frase curta de até 180 caracteres) e summary (2 a 3 frases curtas)."
    )
    body = {
        "model": OPENAI_MODEL,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps({"articles": payload}, ensure_ascii=False)}
        ]
    }
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
        json=body, timeout=90
    )
    response.raise_for_status()
    data = response.json()
    content = data["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    return {x["id"]: x for x in parsed.get("items", []) if isinstance(x, dict) and x.get("id")}


def main():
    previous = {"articles": []}
    if OUT.exists():
        try:
            previous = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            pass
    old_articles = previous.get("articles", [])
    old_by_url = {a.get("url"): a for a in old_articles if a.get("url")}

    gathered, seen = [], set()
    errors = []
    for category, query, tone in CATEGORIES:
        try:
            for article in fetch_category(category, query, tone):
                if article["url"] in seen:
                    continue
                seen.add(article["url"])
                gathered.append(article)
        except Exception as exc:
            errors.append(f"{category}: {exc}")
            print(f"AVISO: falha ao consultar {category}: {exc}")

    # Preserva notícias existentes se um feed falhar temporariamente.
    merged = []
    new_items = []
    for item in gathered:
        old = old_by_url.get(item["url"])
        if old:
            # Atualiza metadados, preserva resumo já produzido pela IA.
            old.update({k: v for k, v in item.items() if v})
            merged.append(old)
        else:
            item["dek"] = item["snippet"][:175] or "Acesse a fonte original para consultar os detalhes desta notícia."
            item["summary"] = item["snippet"] or "O título indica o assunto desta publicação. Consulte a fonte original para ler a cobertura completa."
            item["summary_by"] = "descrição da fonte"
            merged.append(item)
            new_items.append(item)

    # Mantém no catálogo as notícias recentes que saíram do topo do feed,
    # para formar um histórico curto sem apagar tudo a cada execução.
    current_urls = {a.get("url") for a in merged}
    for old in old_articles:
        old_url = old.get("url")
        if not old_url or old_url in current_urls:
            continue
        try:
            old_dt = datetime.fromisoformat(old.get("published", "").replace("Z", "+00:00"))
            if old_dt.tzinfo is None:
                old_dt = old_dt.replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - old_dt.astimezone(timezone.utc)).total_seconds() <= 72 * 3600:
                merged.append(old)
                current_urls.add(old_url)
        except Exception:
            continue

    # Se todos os feeds falharem, não apaga a última edição válida.
    if not gathered and old_articles:
        merged = old_articles

    if OPENAI_API_KEY and new_items:
        try:
            ai = summarize_with_ai(new_items[:40])
            for item in new_items:
                result = ai.get(item["id"])
                if result:
                    item["dek"] = clean_text(result.get("dek", ""))[:220] or item["dek"]
                    item["summary"] = clean_text(result.get("summary", ""))[:900] or item["summary"]
                    item["summary_by"] = "resumo assistido por IA"
        except Exception as exc:
            print(f"AVISO: IA indisponível; mantendo descrições das fontes: {exc}")
    elif not OPENAI_API_KEY:
        print("AVISO: OPENAI_API_KEY não configurada; serão usados trechos das fontes, sem resumo por IA.")

    merged.sort(key=lambda a: a.get("published", ""), reverse=True)
    # Deduplicação final e limite do histórico.
    final, used = [], set()
    for item in merged:
        url = item.get("url")
        if url and url not in used:
            used.add(url)
            final.append(item)
        if len(final) >= MAX_TOTAL:
            break

    output = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "timezone": "UTC",
        "categories": [c[0] for c in CATEGORIES],
        "articles": final,
        "feed_warnings": errors
    }
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Catálogo atualizado: {len(final)} notícias; {len(new_items)} novas; {len(errors)} avisos de feed.")

if __name__ == "__main__":
    main()
