"""
Hämtar färsk viltolycksdata från Nationella viltolycksrådets statistikportal
och uppdaterar den lokala rådatafilen (viltolyckor/data/viltolyckor.parquet).

Hämtar alltid innevarande år och föregående år (för att fånga sena
rapporteringar inom ramen för den kända rapporteringsfördröjningen på upp
till 2 månader) och ersätter bara dessa år i den lokala filen — övriga år
lämnas orörda.

Om skriptet körs inuti ett git-repo med en fjärr (remote) konfigurerad,
committas och pushas den uppdaterade filen automatiskt — det är så en
driftsatt version (t.ex. Streamlit Community Cloud, som byggs om vid ny
commit) får tag i färsk data. Körs skriptet utanför ett git-repo uppdateras
bara den lokala filen.

Använd --alla-ar för att bygga om hela filen från grunden (2015 till idag).
Källa: Nationella viltolycksrådet, viltolycka.se
"""

import argparse
import datetime
import io
import os
import shutil
import subprocess
import sys

import pandas as pd
import requests
from bs4 import BeautifulSoup

EXPORT_URL = "https://statistik.viltolycka.se/statistik/excelrapport/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(SCRIPT_DIR, "data", "viltolyckor.parquet")
DATA_PATH_RELATIV = os.path.join("data", "viltolyckor.parquet")  # relativt repo-roten, för git-kommandon
FORSTA_AR = 2015

# Måste matcha `cols` i load_data() i app.py. Övriga kolumner i källdatan (RT90-koordinater,
# ElementId, DjurID m.fl.) används inte av appen och orsakar dessutom typkonflikter mellan
# olika års-uttag när de sparas — de plockas därför bort innan datan lagras.
KOLUMNER_ATT_BEHALLA = [
    "OlycksID", "Typ av olycka", "Datum", "Län", "Kommun", "Viltslag",
    "Lat WGS84", "Long WGS84", "Kön", "Årsunge",
    "Vad har skett med viltet", "Europaväg",
]


def _hidden_och_select_falt(soup: BeautifulSoup) -> dict:
    falt = {}
    for inp in soup.find_all("input"):
        namn = inp.get("name")
        if namn and inp.get("type") in ("hidden", "text"):
            falt[namn] = inp.get("value", "")
    for sel in soup.find_all("select"):
        namn = sel.get("name")
        if namn:
            vald = sel.find("option", selected=True)
            falt[namn] = vald.get("value") if vald else sel.find("option").get("value")
    return falt


def hamta_ar(session: requests.Session, ar: int) -> bytes:
    """Hämtar rådata-CSV för ett enskilt år direkt från viltolycka.se."""
    r1 = session.get(EXPORT_URL, timeout=30)
    r1.raise_for_status()
    soup = BeautifulSoup(r1.text, "html.parser")
    falt = _hidden_och_select_falt(soup)

    falt["ctl01$ctl11$radRange"] = "0"
    falt["ctl01$ctl11$lstYears"] = str(ar)
    falt["ctl01$ctl11$btnGetYearCSV"] = "Ladda ner CSV-fil"

    r2 = session.post(EXPORT_URL, data=falt, headers={**HEADERS, "Referer": EXPORT_URL}, timeout=120)
    r2.raise_for_status()
    if "text/csv" not in r2.headers.get("Content-Type", ""):
        raise RuntimeError(
            f"Fick inte en CSV-fil tillbaka för år {ar} (Content-Type: {r2.headers.get('Content-Type')}). "
            "Sidans formulärfält kan ha ändrats."
        )
    return r2.content


def las_csv_bytes(data: bytes) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(data), sep=";", encoding="cp1252", usecols=KOLUMNER_ATT_BEHALLA)


def _kor_git(*args) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=SCRIPT_DIR
    )


def commita_och_pusha(path: str) -> None:
    """Committar och pushar path om vi är i ett git-repo med en remote. No-op annars."""
    ar_repo = _kor_git("rev-parse", "--is-inside-work-tree")
    if ar_repo.returncode != 0:
        print("\n(Inget git-repo hittat — bara den lokala filen uppdaterades. "
              "En eventuell driftsatt version måste uppdateras separat.)")
        return

    remotes = _kor_git("remote")
    if not remotes.stdout.strip():
        print("\n(Git-repo hittat, men ingen remote konfigurerad — kunde inte pusha. "
              "Bara den lokala filen uppdaterades.)")
        return

    status = _kor_git("status", "--porcelain", "--", path)
    if not status.stdout.strip():
        print("\n(Inga faktiska ändringar i filen sedan senaste commit — inget att pusha.)")
        return

    add = _kor_git("add", path)
    if add.returncode != 0:
        print(f"\nVARNING: 'git add' misslyckades: {add.stderr}", file=sys.stderr)
        return

    idag = datetime.date.today().isoformat()
    commit = _kor_git("commit", "-m", f"Uppdatera viltolycksdata ({idag})")
    if commit.returncode != 0:
        print(f"\nVARNING: 'git commit' misslyckades: {commit.stderr}", file=sys.stderr)
        return

    push = _kor_git("push")
    if push.returncode != 0:
        print(
            f"\nVARNING: datan committades lokalt men kunde inte pushas "
            f"(t.ex. autentisering eller nätverk): {push.stderr}",
            file=sys.stderr,
        )
        return

    print("\nÄndringarna committades och pushades — en driftsatt app som byggs om vid ny "
          "commit (t.ex. Streamlit Community Cloud) plockar upp datan automatiskt.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--alla-ar", action="store_true",
        help="Hämta om alla år från 2015 till idag istället för bara de senaste två.",
    )
    parser.add_argument(
        "--ingen-git", action="store_true",
        help="Committa/pusha inte ens om ett git-repo finns.",
    )
    args = parser.parse_args()

    aktuellt_ar = datetime.date.today().year
    if args.alla_ar:
        ar_att_hamta = list(range(FORSTA_AR, aktuellt_ar + 1))
    else:
        ar_att_hamta = sorted({aktuellt_ar - 1, aktuellt_ar})

    print(f"Hämtar år {ar_att_hamta} från {EXPORT_URL} ...")

    session = requests.Session()
    session.headers.update(HEADERS)

    nya_delar = []
    for ar in ar_att_hamta:
        try:
            raw = hamta_ar(session, ar)
        except Exception as e:
            print(f"  FEL vid hämtning av år {ar}: {e}", file=sys.stderr)
            continue
        df_ar = las_csv_bytes(raw)
        print(f"  År {ar}: {len(df_ar):,} rader hämtade".replace(",", " "))
        nya_delar.append(df_ar)

    if not nya_delar:
        print("Inget kunde hämtas — avbryter utan att röra den befintliga filen.", file=sys.stderr)
        sys.exit(1)

    nya_data = pd.concat(nya_delar, ignore_index=True)

    try:
        befintlig = pd.read_parquet(DATA_PATH)
    except FileNotFoundError:
        befintlig = pd.DataFrame(columns=nya_data.columns)

    if args.alla_ar or befintlig.empty:
        resultat = nya_data
    else:
        # OBS: OlycksID är inte globalt unikt (samma nummerintervall återanvänds för olika år,
        # troligen ett ärendenummer som återställs årsvis) — kan alltså INTE användas för att
        # matcha rader mellan år. Filtrera istället på kalenderåret i Datum-fältet. Sajtens eget
        # årsfilter följer i sällsynta fall ärendets handläggningsår snarare än olycksdatumet,
        # vilket kan ge en försumbar avvikelse (observerat: <0.1% av radantalet) kring årsskiften.
        ar_som_ersatts = pd.to_datetime(
            befintlig["Datum"], format="%Y-%m-%d %H:%M", errors="coerce"
        ).dt.year
        kvar = befintlig[~ar_som_ersatts.isin(ar_att_hamta)]
        resultat = pd.concat([kvar, nya_data], ignore_index=True)

    if not befintlig.empty and len(resultat) < len(befintlig) * 0.9:
        print(
            f"VARNING: den nya datan ({len(resultat):,} rader) är över 10% mindre än den befintliga "
            f"({len(befintlig):,} rader). Avbryter utan att skriva, något verkar ha gått fel.".replace(",", " "),
            file=sys.stderr,
        )
        sys.exit(1)

    backup_tagen = not befintlig.empty
    if backup_tagen:
        shutil.copy(DATA_PATH, DATA_PATH + ".bak")

    resultat.to_parquet(DATA_PATH, index=False)
    print(f"\nKlart. {DATA_PATH} innehåller nu {len(resultat):,} rader totalt.".replace(",", " "))
    if backup_tagen:
        print(f"(Föregående version sparad som {DATA_PATH}.bak.)")
    print("(Källa: Nationella viltolycksrådet, viltolycka.se)")

    if not args.ingen_git:
        commita_och_pusha(DATA_PATH_RELATIV)


if __name__ == "__main__":
    main()
