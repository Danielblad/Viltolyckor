import os
import threading
import time
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(APP_DIR, "data", "viltolyckor.parquet")

MONTH_NAMES = [
    "Januari", "Februari", "Mars", "April", "Maj", "Juni",
    "Juli", "Augusti", "September", "Oktober", "November", "December",
]
WEEKDAY_NAMES = ["Måndag", "Tisdag", "Onsdag", "Torsdag", "Fredag", "Lördag", "Söndag"]
HOUR_NAMES = [f"{h:02d}" for h in range(24)]

# Officiella definitioner från Nationella viltolycksrådet (forklarande-texter-utfall.pdf)
UTFALL_FORKLARING = {
    "Avlivat": "Viltet har avlivats av jägaren.",
    "Bedöms oskadat": "Viltet kan bedömas som oskadat först när jägaren sett viltet eller när den sammanlagda bedömningen tydligt tyder på att viltet inte tagit skada av olyckan.",
    "Bedöms skadat ej påträffats": "Eftersöket har fått avbrytas trots att viltet bedöms eller konstateras skadat, utan att det kunnat avlivas.",
    "Ej påträffat": "Viltet har inte kunnat påträffas och skadeläget har därför inte kunnat bedömas.",
    "Dött på olycksplatsen": "Djuret återfinns dött på eller i direkt anslutning till olycksplatsen.",
    "Påträffat dött": "Viltet påträffas dött under eftersöket.",
    "Olycksplats ej påträffad": "Olycksplatsen har inte kunnat hittas (ej utmärkt, felaktigt utmärkt eller bristande platsangivelse). Tillkom som kategori i februari 2026 — jämförelser bakåt i tiden underskattar därför denna kategori.",
}
UTFALL_TOOLTIP = "\n\n".join(f"**{k}** — {v}" for k, v in UTFALL_FORKLARING.items())

# Pluralform per viltslag, för korrekt svensk grammatik i löptext (t.ex. "andel järvar",
# inte det påhittade "andel järv"). Rådjur/Vildsvin/Mufflonfår/Övriga djur böjs inte i plural.
VILTSLAG_PLURAL = {
    "Rådjur": "rådjur",
    "Vildsvin": "vildsvin",
    "Älg": "älgar",
    "Dovhjort": "dovhjortar",
    "Övriga djur": "övriga djur",
    "Kronhjort": "kronhjortar",
    "Utter": "uttrar",
    "Örn": "örnar",
    "Lo": "lodjur",
    "Varg": "vargar",
    "Björn": "björnar",
    "Mufflonfår": "mufflonfår",
    "Järv": "järvar",
}

# Etikett (visas för användaren) -> kolumnnamn i den städade dataframen
DIMENSIONS = {
    "Viltslag": "Viltslag",
    "Län": "Län",
    "Kommun": "Kommun",
    "Typ av olycka": "Typ av olycka",
    "Kön": "Kön",
    "Årsunge": "Årsunge",
    "Vad har skett med viltet": "Vad har skett med viltet",
    "Europaväg": "Europaväg",
    "År": "ÅrVisning",
    "Månad": "Månad",
    "Veckodag": "Veckodag",
    "Timme": "TimmeVisning",
}
COLUMN_TO_LABEL = {col: label for label, col in DIMENSIONS.items()}

# Dimensioner med en naturlig ordning - visas alltid i sin helhet, aldrig beskurna till "topp N"
ORDNADE_DIMENSIONER_LABELS = {"Månad", "Veckodag", "Timme", "År"}
ORDNADE_KATEGORIER = {
    "Månad": MONTH_NAMES,
    "Veckodag": WEEKDAY_NAMES,
    "Timme": HOUR_NAMES,
}

# Naturtema: skogsgrönt, jordbrunt, sol, himmel, bär m.fl.
PALETTE = [
    "#2E7D32", "#F57C00", "#6D4C41", "#0277BD", "#C62828",
    "#8E24AA", "#00897B", "#AFB42B", "#5D4037", "#455A64",
    "#EF6C00", "#00ACC1",
]
px.defaults.color_discrete_sequence = PALETTE
px.defaults.template = "plotly_white"

EXTRA_LABELS = {"Antal": "Antal djur", "Andel": "Andel (%)", "Lat": "Latitud", "Long": "Longitud"}
LABELS = {**COLUMN_TO_LABEL, **EXTRA_LABELS}

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@500;600;700&family=Nunito:wght@400;600;700;800&display=swap');

:root {
    --skog: #1B7A43;
    --skog-mork: #0F5C31;
    --accent: #C62828;
    --text: #1F2937;
    --bakgrund: #F7F8F6;
}

html, body, .stApp { font-family: 'Nunito', sans-serif; background-color: var(--bakgrund); color: var(--text); }
h1, h2, h3, h4, .banner h1 { font-family: 'Poppins', sans-serif; font-weight: 600; }
#MainMenu, footer { visibility: hidden; }

/* Låt allt innehåll krympa med skärmen istället för att tvinga fram horisontell scroll */
.block-container { max-width: 100%; padding-left: 1rem; padding-right: 1rem; }

.banner {
    background: linear-gradient(100deg, var(--skog) 0%, var(--skog-mork) 100%);
    padding: 1.3rem 1.8rem;
    border-radius: 12px;
    color: white;
    margin-bottom: 1.2rem;
}
.banner h1 { margin: 0; font-size: clamp(1.3rem, 3.4vw, 1.8rem); line-height: 1.2; }
.banner p { margin: 0.3rem 0 0 0; opacity: 0.92; font-size: clamp(0.8rem, 2.1vw, 0.95rem); }

div[data-testid="stMetric"] {
    background-color: white;
    border-left: 4px solid var(--skog);
    border-radius: 8px;
    padding: 0.8rem 1.05rem;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
div[data-testid="stMetricValue"] {
    font-size: clamp(0.95rem, 2.4vw, 1.4rem); font-family: 'Poppins', sans-serif; font-weight: 600;
    white-space: normal !important; overflow: visible !important; text-overflow: clip !important;
    line-height: 1.2;
}
div[data-testid="stMetricValue"] > div { white-space: normal !important; overflow: visible !important; text-overflow: clip !important; }

.stTabs [role="tablist"], .stTabs [data-baseweb="tab-list"] {
    flex-wrap: nowrap; overflow-x: auto; gap: 2px;
    background: #EEF1EC; padding: 4px; border-radius: 8px;
}
.stTabs [role="tab"], .stTabs [data-baseweb="tab"] {
    font-weight: 600; font-size: clamp(0.8rem, 2vw, 0.95rem); white-space: nowrap;
    border-radius: 6px !important; padding: 0.4rem 1rem !important;
    transition: background-color 0.15s ease, color 0.15s ease;
}
.stTabs [role="tab"][aria-selected="true"], .stTabs [data-baseweb="tab"][aria-selected="true"] {
    background: var(--skog) !important; color: white !important;
}
/* Den inbyggda "glidande" markören mäts fram med JS och kan hamna fel storlek
   (t.ex. innan webbfonten hunnit laddas) så att den inte täcker hela texten.
   Bakgrunden sätts istället direkt på fliken ovan, så markören döljs helt. */
.stTabs .react-aria-SelectionIndicator { display: none !important; }
.stTabs [data-baseweb="tab-highlight"] { display: none; }
.stTabs [data-baseweb="tab-border"] { display: none; }

.stButton button, .stDownloadButton button {
    border-radius: 6px !important; font-weight: 600 !important; border: none !important;
    background: var(--skog-mork) !important;
    color: white !important; transition: background-color 0.15s ease !important;
}
.stButton button:hover, .stDownloadButton button:hover { background: var(--skog) !important; }

section[data-testid="stSidebar"] {
    background: #F1F4EF;
    border-right: 1px solid #DDE3D8;
}

.fact-card {
    background: white; border-radius: 8px; padding: 0.85rem 1.05rem;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06); transition: box-shadow 0.15s ease;
}
.fact-card:hover { box-shadow: 0 3px 10px rgba(0,0,0,0.1); }

.standout-card {
    background: white; border-radius: 8px; padding: 1.1rem 1.4rem;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06); margin-bottom: 1rem;
}

.promo-banner {
    background: white; border-left: 4px solid var(--accent);
    border-radius: 8px; padding: 0.9rem 1.4rem; color: var(--text); margin-bottom: 1.2rem;
    display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.5rem;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}

/* Låt ett vertikalt svep över ett diagram fortsätta scrolla sidan istället för att
   fastna i diagrammets egen pan/zoom-hantering (annars kan man "fastna" på ett
   diagram på mobil och inte komma vidare nedåt på sidan). */
div[data-testid="stPlotlyChart"], div[data-testid="stPlotlyChart"] > div, .js-plotly-plot {
    touch-action: pan-y !important;
}

/* Gör sidopanelens fäll-ut-pil (syns när panelen är hopfälld) tydligare - annars är
   den en liten, lätt att missa ikon, särskilt på mobil. */
[data-testid="stSidebarCollapsedControl"] {
    background: white !important;
    border: 2px solid var(--skog) !important;
    border-radius: 8px !important;
    box-shadow: 0 2px 6px rgba(0,0,0,0.15) !important;
}
[data-testid="stSidebarCollapsedControl"] svg { color: var(--skog) !important; }

.scroll-hint { text-align: center; color: #6B7280; font-size: 0.85rem; margin: 0.4rem 0 0.8rem 0; }

/* Mobil/smal skärm: mindre marginaler och tätare kort så mer ryms utan att klippas */
@media (max-width: 640px) {
    .block-container { padding-top: 1.5rem; padding-left: 0.6rem; padding-right: 0.6rem; }
    .banner { padding: 1rem 1.2rem; border-radius: 10px; }
    div[data-testid="stMetric"] { padding: 0.55rem 0.75rem; }
}
</style>
"""

MAX_MAP_POINTS = 20000
MAX_TABLE_ROWS = 3000
MAP_HEIGHT = 500
KALLA_TEXT = "Källa: Nationella viltolycksrådet, viltolycka.se"
KALLA_URL = "viltolycka.se"
BESOKSLOGG_PATH = os.path.join(APP_DIR, "besoksstatistik.log")


@st.cache_resource
def _besokslas() -> threading.Lock:
    """En enda delad lås-instans för alla samtidiga sessioner (till skillnad från
    st.cache_data kopierar st.cache_resource INTE returvärdet — alla anrop, från alla
    användare, får samma lås-objekt). Krävs eftersom flera användare kan besöka appen
    samtidigt och annars kan hamna i att skriva till loggfilen på en gång."""
    return threading.Lock()


def logga_besok_och_hamta_antal() -> int:
    """Loggar ett besök (en gång per webbläsarsession) och returnerar totalt antal besök.

    OBS: loggen är en lokal fil och nollställs varje gång appen byggs om på nytt (t.ex. vid
    en driftsatt version på Streamlit Community Cloud som byggs om vid en ny commit). Räknar
    alltså besök sedan senaste ombyggnad, inte sedan lanseringen."""
    las = _besokslas()
    if not st.session_state.get("besok_loggat"):
        st.session_state["besok_loggat"] = True
        try:
            with las:
                with open(BESOKSLOGG_PATH, "a", encoding="utf-8") as f:
                    f.write(f"{datetime.now().isoformat(timespec='seconds')}\n")
                    f.flush()
        except OSError:
            pass
    try:
        with las:
            with open(BESOKSLOGG_PATH, encoding="utf-8") as f:
                return sum(1 for _ in f)
    except FileNotFoundError:
        return 0


def _las_parquet_med_omforsok(path: str, columns: list, forsok: int = 5, vantetid: float = 1.0) -> pd.DataFrame:
    """Läser en parquet-fil med återförsök. Skyddar mot att appen läser filen precis
    medan en driftsättning fortfarande håller på att skriva den till disk (race
    condition vid omstart efter en ny git-pull), vilket annars kan se ut som en
    korrupt/tom fil trots att den egentligen är helt intakt."""
    senaste_fel = None
    for i in range(forsok):
        try:
            return pd.read_parquet(path, columns=columns)
        except Exception as e:
            senaste_fel = e
            if i < forsok - 1:
                time.sleep(vantetid)
    raise senaste_fel


@st.cache_resource(show_spinner="Läser in viltolycksdata...")
def load_data(path: str, senast_andrad: float) -> pd.DataFrame:
    """OBS: cache_resource (inte cache_data) med flit — datan är stor (750 000+ rader) och
    ska aldrig kopieras per session/besökare, bara läsas. Delas därför som EN gemensam
    instans mellan alla samtidiga användare istället för att varje session får sin egen
    kopia i minnet (skulle annars multiplicera minnesanvändningen med antalet besökare).
    Kräver att koden aldrig muterar df i efterhand — all filtrering sker via df[mask],
    som alltid skapar en ny, oberoende dataframe."""
    cols = [
        "OlycksID", "Typ av olycka", "Datum", "Län", "Kommun", "Viltslag",
        "Lat WGS84", "Long WGS84", "Kön", "Årsunge",
        "Vad har skett med viltet", "Europaväg",
    ]
    df = _las_parquet_med_omforsok(path, cols)

    df["Datum"] = pd.to_datetime(df["Datum"], format="%Y-%m-%d %H:%M", errors="coerce")
    df["Lat"] = pd.to_numeric(df["Lat WGS84"].astype(str).str.replace(",", "."), errors="coerce")
    df["Long"] = pd.to_numeric(df["Long WGS84"].astype(str).str.replace(",", "."), errors="coerce")
    df.loc[(df["Lat"] == 0) | (df["Long"] == 0), ["Lat", "Long"]] = pd.NA

    ar = df["Datum"].dt.year
    manad = df["Datum"].dt.month
    veckodag = df["Datum"].dt.dayofweek
    timme = df["Datum"].dt.hour

    df["År"] = ar
    df["ÅrVisning"] = ar.astype("Int64").astype(str).where(ar.notna())
    # OlycksID är bara unikt inom ett kalenderår (källans nummerserie återanvänds årsvis),
    # så ett globalt unikt olycks-ID måste kombinera år + OlycksID.
    df["OlycksID_Unik"] = df["ÅrVisning"].astype(str) + "_" + df["OlycksID"].astype(str)
    df["Månad"] = pd.Categorical(
        manad.map(lambda m: MONTH_NAMES[m - 1] if pd.notna(m) else None),
        categories=MONTH_NAMES, ordered=True,
    )
    df["Veckodag"] = pd.Categorical(
        veckodag.map(lambda d: WEEKDAY_NAMES[d] if pd.notna(d) else None),
        categories=WEEKDAY_NAMES, ordered=True,
    )
    df["TimmeVisning"] = pd.Categorical(
        timme.map(lambda h: f"{int(h):02d}" if pd.notna(h) else None),
        categories=HOUR_NAMES, ordered=True,
    )

    # Minnesoptimering: lågkardinalitets textkolumner som kategorityp (bråkdel av minnet
    # för samma innehåll), koordinater som float32 (halva minnet, gott om precision kvar
    # för en karta). Sänker minnesavtrycket för hela dataframen med ca 3x.
    for kol in [
        "Typ av olycka", "Län", "Kommun", "Viltslag", "Kön", "Årsunge",
        "Vad har skett med viltet", "Europaväg", "ÅrVisning",
    ]:
        df[kol] = df[kol].astype("category")
    df["Lat"] = df["Lat"].astype("float32")
    df["Long"] = df["Long"].astype("float32")

    return df.drop(columns=["Lat WGS84", "Long WGS84"])


def apply_filter(df: pd.DataFrame, column: str, selected: list) -> pd.DataFrame:
    if selected:
        return df[df[column].isin(selected)]
    return df


CHART_CONFIG = {
    "displaylogo": False,
    "scrollZoom": False,
    "doubleClick": False,
    "modeBarButtonsToRemove": [
        "zoom2d", "pan2d", "select2d", "lasso2d", "zoomIn2d", "zoomOut2d",
        "autoScale2d", "resetScale2d", "zoomInGeo", "zoomOutGeo",
    ],
}


def visa_diagram(fig, **kwargs):
    """Renderar ett Plotly-diagram med all zoom/pan avstängd (dragmode=False +
    borttagna zoomknappar), så ett svep över diagrammet alltid fortsätter scrolla
    sidan istället för att fastna i diagrammets egen interaktion — särskilt viktigt
    på mobil. Hover/tooltips fungerar fortfarande som vanligt."""
    fig.update_layout(dragmode=False)
    kwargs.setdefault("width", "stretch")
    kwargs["config"] = {**CHART_CONFIG, **kwargs.get("config", {})}
    st.plotly_chart(fig, **kwargs)


def kategoriordning(label: str, fallback_index) -> list:
    return ORDNADE_KATEGORIER.get(label, list(fallback_index))


st.set_page_config(
    page_title="Viltolyckor i Sverige", page_icon="🦌", layout="wide",
    initial_sidebar_state="collapsed",
)
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

df = load_data(DATA_PATH, os.path.getmtime(DATA_PATH))
ORDNADE_KATEGORIER["År"] = sorted(df["ÅrVisning"].dropna().unique())

ANTAL_BESOK = logga_besok_och_hamta_antal()

RAPPORTERINGSFORDROJNING_DAGAR = 60
SENASTE_KOMPLETTA_DATUM = df["Datum"].max() - pd.Timedelta(days=RAPPORTERINGSFORDROJNING_DAGAR)
ANTAL_UNIKA_OLYCKOR_TOTALT = df["OlycksID_Unik"].nunique()

st.markdown(
    f"""
    <div class="banner">
        <h1>🦌 Viltolyckor i Sverige</h1>
        <p>Utforska {len(df):,} djur inblandade i {ANTAL_UNIKA_OLYCKOR_TOTALT:,} registrerade viltolyckor,
        {df['Datum'].min():%Y-%m-%d} – {df['Datum'].max():%Y-%m-%d}.</p>
        <p style="margin-top:0.5rem;font-weight:600;">👈 Tryck på pilen uppe till vänster för att öppna filtren
        och göra ett urval — välj sedan flik nedanför för olika sätt att analysera datan.</p>
    </div>
    """.replace(",", " "),
    unsafe_allow_html=True,
)

with st.expander("ℹ️ Om datan och källan"):
    st.markdown(
        f"""
**{KALLA_TEXT}** — vid all vidare spridning av statistiken ska källan anges.

- **Rapporteringsfördröjning:** Uppdragstagare kan ta upp till {RAPPORTERINGSFORDROJNING_DAGAR} dagar (2 månader) på sig att
  rapportera in en olycka. Statistik för de senaste {RAPPORTERINGSFORDROJNING_DAGAR} dagarna är därför ofullständig.
- **Djur vs. olyckor:** Varje rad i datat är **ett djur** som varit inblandat i en viltolycka, inte en olycka i sig.
  Sedan 2021 kan flera djur höra till samma olyckstillfälle (samma OlycksID) — totalt i hela datasetet är det
  {len(df):,} djur men bara {ANTAL_UNIKA_OLYCKOR_TOTALT:,} unika olyckor. De flesta diagram i appen räknar djur
  (det mest detaljerade måttet), utom där det uttryckligen står "unika olyckor".
- **"Övriga djur":** En samlingskategori för statens vilt, eller djur som vid platsbesöket visade sig inte vara
  anmälningspliktiga enligt Jaktförordningen — inte en egen djurart.
- **"Olycksplats ej påträffad":** Tillkom som utfall i februari 2026. Jämförelser över tid underskattar därför
  denna kategori för perioden innan dess.
- **Varför start 2015:** Det året blev polismyndigheterna en enda myndighet och började hantera viltolyckor
  enhetligt. Data innan dess kan inte garanteras vara korrekt och redovisas därför inte.
- **Uppdateringsfrekvens:** Källans egen statistik uppdateras varje natt. Den här appen använder en lokal kopia
  av rådatafilen och uppdateras bara när den filen ersätts (se filens ändringsdatum: {pd.Timestamp(os.path.getmtime(DATA_PATH), unit="s"):%Y-%m-%d %H:%M}).

**Förklaring till "Vad har skett med viltet":**
        """
    )
    for utfall, forklaring in UTFALL_FORKLARING.items():
        st.markdown(f"- **{utfall}** — {forklaring}")
    st.caption("Frågor om själva statistiken besvaras av Nationella viltolycksrådet, inte av den här appen.")

st.sidebar.header("🔎 Filter")
st.sidebar.caption("Lämna ett filter tomt för att inkludera alla värden.")

year_min, year_max = int(df["År"].min()), int(df["År"].max())
ar_intervall = st.sidebar.select_slider(
    "Årsintervall", options=list(range(year_min, year_max + 1)), value=(year_min, year_max)
)

selected_lan = st.sidebar.multiselect("Län", sorted(df["Län"].dropna().unique()), placeholder="Alla län")
kommun_pool = df[df["Län"].isin(selected_lan)] if selected_lan else df
selected_kommun = st.sidebar.multiselect(
    "Kommun", sorted(kommun_pool["Kommun"].dropna().unique()), placeholder="Alla kommuner"
)
selected_viltslag = st.sidebar.multiselect(
    "Viltslag", sorted(df["Viltslag"].dropna().unique()), placeholder="Alla viltslag",
    help="'Övriga djur' är statens vilt eller djur som visat sig inte vara anmälningspliktiga enligt Jaktförordningen — inte en egen art.",
)
selected_typ = st.sidebar.multiselect(
    "Typ av olycka", sorted(df["Typ av olycka"].dropna().unique()), placeholder="Alla typer"
)
selected_kon = st.sidebar.multiselect("Kön", sorted(df["Kön"].dropna().unique()), placeholder="Alla")
selected_arsunge = st.sidebar.multiselect("Årsunge", sorted(df["Årsunge"].dropna().unique()), placeholder="Alla")
selected_utfall = st.sidebar.multiselect(
    "Vad har skett med viltet",
    sorted(df["Vad har skett med viltet"].dropna().unique()),
    placeholder="Alla utfall",
    help=UTFALL_TOOLTIP,
)
selected_europavag = st.sidebar.multiselect(
    "Europaväg", sorted(df["Europaväg"].dropna().unique()), placeholder="Alla"
)

st.sidebar.divider()
st.sidebar.caption(
    f"👀 {ANTAL_BESOK:,} besök sedan senaste omstart av appen.".replace(",", " ")
)

filtered = df[(df["År"] >= ar_intervall[0]) & (df["År"] <= ar_intervall[1])]
filtered = apply_filter(filtered, "Län", selected_lan)
filtered = apply_filter(filtered, "Kommun", selected_kommun)
filtered = apply_filter(filtered, "Viltslag", selected_viltslag)
filtered = apply_filter(filtered, "Typ av olycka", selected_typ)
filtered = apply_filter(filtered, "Kön", selected_kon)
filtered = apply_filter(filtered, "Årsunge", selected_arsunge)
filtered = apply_filter(filtered, "Vad har skett med viltet", selected_utfall)
filtered = apply_filter(filtered, "Europaväg", selected_europavag)

INGA_FILTER_AKTIVA = (
    ar_intervall == (year_min, year_max)
    and not selected_lan and not selected_kommun and not selected_viltslag
    and not selected_typ and not selected_kon and not selected_arsunge
    and not selected_utfall and not selected_europavag
)

# Kategorikolumner behåller hela df:s ursprungliga kategorilista även efter filtrering
# (t.ex. alla 291 kommuner, även om urvalet bara innehåller data från en). Utan att städa
# bort de nu tomma kategorierna skulle value_counts()/groupby m.fl. kunna räkna med
# "spökkategorier" som har noll träffar i just detta urval.
for _kategorikolumn in filtered.select_dtypes(include="category").columns:
    filtered[_kategorikolumn] = filtered[_kategorikolumn].cat.remove_unused_categories()

st.caption(f"Visar {len(filtered):,} av {len(df):,} djur utifrån valda filter.".replace(",", " "))

if filtered.empty:
    st.warning("Inga djur matchar de valda filtren. Justera filtren i sidopanelen.")
    st.stop()

# Trend: senaste hela kalenderåret mot föregående, inom nuvarande filterurval.
# Ett stigande antal olyckor är en försämring, inte en förbättring - därför delta_color="inverse"
# (fler olyckor -> rött, färre -> grönt), tvärtom mot st.metrics standardfärgning.
delta_djur = delta_olyckor = delta_period = None
ar_lista = sorted(int(a) for a in filtered["År"].dropna().unique())
if len(ar_lista) >= 2:
    sista_ar = ar_lista[-1]
    sista_datum = filtered.loc[filtered["År"] == sista_ar, "Datum"].max()
    if (sista_datum.month, sista_datum.day) < (12, 25):
        sista_ar = ar_lista[-2]
    tidigare_ar = [a for a in ar_lista if a < sista_ar]
    if tidigare_ar:
        foreg_ar = tidigare_ar[-1]
        djur_sista = int((filtered["År"] == sista_ar).sum())
        djur_foreg = int((filtered["År"] == foreg_ar).sum())
        olyckor_sista = filtered.loc[filtered["År"] == sista_ar, "OlycksID_Unik"].nunique()
        olyckor_foreg = filtered.loc[filtered["År"] == foreg_ar, "OlycksID_Unik"].nunique()
        if djur_foreg > 0 and olyckor_foreg > 0:
            delta_djur = (djur_sista - djur_foreg) / djur_foreg * 100
            delta_olyckor = (olyckor_sista - olyckor_foreg) / olyckor_foreg * 100
            delta_period = f"{foreg_ar} → {sista_ar}"

k1, k2, k3 = st.columns(3)
k1.metric(
    "Antal djur i olyckor", f"{len(filtered):,}".replace(",", " "),
    delta=f"{delta_djur:+.1f}% ({delta_period})" if delta_djur is not None else None,
    delta_color="inverse",
    help="Varje rad i rådatan är ett djur. Se 'Varav unika olyckor' för antalet faktiska olyckstillfällen. "
         "Trenden jämför de två senaste hela kalenderåren i urvalet.",
)
antal_unika = filtered["OlycksID_Unik"].nunique()
k2.metric(
    "Varav unika olyckor", f"{antal_unika:,}".replace(",", " "),
    delta=f"{delta_olyckor:+.1f}% ({delta_period})" if delta_olyckor is not None else None,
    delta_color="inverse",
    help="Sedan 2021 kan flera djur rapporteras på samma olyckstillfälle (samma OlycksID), så detta tal kan vara lägre än antal djur.",
)
k3.metric("Vanligaste viltslag", filtered["Viltslag"].mode().iat[0])

st.markdown('<p class="scroll-hint">⌄ Fler analyser och diagram nedanför ⌄</p>', unsafe_allow_html=True)

tab_oversikt, tab_lokal, tab_utforska, tab_jamfor, tab_korstabell, tab_karta, tab_data = st.tabs(
    ["🏠 Översikt", "📰 Lokal vinkel", "🔍 Utforska", "⚖️ Jämför", "🔀 Korstabell", "🗺️ Karta", "📄 Data"]
)

with tab_oversikt:
    st.warning(
        f"⚠️ **Statistiken för de senaste {RAPPORTERINGSFORDROJNING_DAGAR} dagarna är ofullständig.** "
        "Uppdragstagare kan ta upp till 2 månader på sig att rapportera in en viltolycka, så de senaste veckornas "
        f"siffror fylls på efter hand och ska inte tolkas som en verklig nedgång. Trendgrafen nedan visar "
        f"därför bara data till och med **{SENASTE_KOMPLETTA_DATUM:%Y-%m-%d}**. ({KALLA_TEXT})"
    )

    st.markdown(
        """
        <div class="promo-banner">
            <div>
                <div style="font-size:1.05rem;font-weight:700;font-family:'Poppins',sans-serif;color:var(--accent);">
                    📰 Nytt: Hitta din lokala vinkel
                </div>
                <div style="font-size:0.92rem;opacity:0.97;margin-top:0.2rem;">
                    Välj ditt län eller din kommun och se exakt vilket mått det sticker ut på i landet —
                    en färdig, citerbar faktapunkt för lokal bevakning av viltolyckor.
                </div>
            </div>
            <div style="font-size:0.95rem;font-weight:800;white-space:nowrap;">👉 Fliken "📰 Lokal vinkel" ovan</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    granularitet = st.radio("Granularitet för trenden", ["År", "Månad", "Vecka"], horizontal=True)
    freq = {"År": "YE", "Månad": "ME", "Vecka": "W"}[granularitet]

    trend_bas = filtered[filtered["Datum"] <= SENASTE_KOMPLETTA_DATUM]
    if trend_bas.empty:
        st.info("Allt i det valda urvalet ligger inom den senaste, ännu ofullständiga rapporteringsperioden.")
    else:
        trend = trend_bas.set_index("Datum").resample(freq).size().reset_index(name="Antal")
        visa_diagram(
            px.line(trend, x="Datum", y="Antal", markers=True, labels=LABELS, title="Djur i viltolyckor över tid"),
        )

    visa_som_oversikt = st.radio(
        "Visa fördelningsdiagrammen som", ["Andel (%)", "Antal"], horizontal=True, key="oversikt_visa_som"
    )

    def _fordelning(kolumn: str) -> pd.DataFrame:
        agg = filtered[kolumn].value_counts().reset_index()
        agg.columns = [kolumn, "Antal"]
        agg["Andel"] = (agg["Antal"] / len(filtered) * 100).round(1)
        if visa_som_oversikt == "Andel (%)":
            agg["Etikett"] = agg["Andel"].map(lambda v: f"{v:.1f}%")
            return agg, "Andel", "Andel (%)"
        agg["Etikett"] = agg["Antal"].map(lambda v: f"{v:,}".replace(",", " "))
        return agg, "Antal", "Antal djur"

    c1, c2 = st.columns(2)
    with c1:
        topp_djur, y_djur, y_djur_titel = _fordelning("Viltslag")
        fig_djur = px.bar(
            topp_djur, x="Viltslag", y=y_djur, labels={**LABELS, y_djur: y_djur_titel},
            title=f"{y_djur_titel} per viltslag (alla)", color="Viltslag", text="Etikett",
        )
        fig_djur.update_layout(showlegend=False)
        visa_diagram(fig_djur)
    with c2:
        topp_lan, y_lan, y_lan_titel = _fordelning("Län")
        fig_lan = px.bar(
            topp_lan, x="Län", y=y_lan, labels={**LABELS, y_lan: y_lan_titel},
            title=f"{y_lan_titel} per län (alla)", color="Län", text="Etikett",
        )
        fig_lan.update_layout(showlegend=False)
        visa_diagram(fig_lan)

    st.markdown("### 🎲 Visste du att...?")
    if not INGA_FILTER_AKTIVA:
        st.info("Fun facts visas bara utan aktiv filtrering just nu, för att undvika missvisande siffror vid vissa urval. Rensa filtren i sidopanelen för att se dem.")
    else:
        st.caption("Baserat på ditt aktuella filterval ovan — kan se annorlunda ut om du ändrar filtren.")

        def _lan_topplista(mask, min_n=50):
            total = filtered.groupby("Län", observed=True).size()
            traff = filtered[mask].groupby("Län", observed=True).size()
            andel = (traff / total * 100).reindex(total.index).fillna(0)
            kandidater = andel[total >= min_n]
            if kandidater.empty:
                return None
            topp = kandidater.idxmax()
            return topp, kandidater.loc[topp]

        fakta = []

        timme_mode = filtered["TimmeVisning"].mode()
        if not timme_mode.empty:
            h = timme_mode.iat[0]
            andel_h = (filtered["TimmeVisning"] == h).mean() * 100
            fakta.append(("🕒", f"Kl. {h}", f"är den vanligaste timmen på dygnet — {andel_h:.1f}% av alla djur i viltolyckor blir påkörda just då."))

        dag_counts = filtered["Veckodag"].value_counts()
        if len(dag_counts) >= 2:
            flest, lugnast = dag_counts.idxmax(), dag_counts.idxmin()
            fakta.append(("📅", flest, f"är den dag flest djur blir inblandade i viltolyckor, medan {lugnast.lower()} är lugnast."))

        manad_mode = filtered["Månad"].mode()
        if not manad_mode.empty:
            m = manad_mode.iat[0]
            andel_m = (filtered["Månad"] == m).mean() * 100
            fakta.append(("🍂", m, f"är den mest olycksdrabbade månaden ({andel_m:.1f}% av alla djur) — troligen kopplat till brunsttid och mörkare kvällar."))

        frekvens_bas = filtered[filtered["Datum"] <= SENASTE_KOMPLETTA_DATUM]
        antal_unika_frekvens = frekvens_bas["OlycksID_Unik"].nunique()
        if antal_unika_frekvens > 1:
            dagar = max((frekvens_bas["Datum"].max() - frekvens_bas["Datum"].min()).days, 1)
            minuter = (dagar * 24 * 60) / antal_unika_frekvens
            fakta.append(("⏱️", f"Var {minuter:.0f}:e minut", "inträffar i snitt en viltolycka någonstans i det valda urvalet (räknat på unika olyckor, baserat på fullständigt rapporterad data)."))

        res = _lan_topplista(filtered["Vad har skett med viltet"] == "Ej påträffat")
        if res:
            lan, andel = res
            fakta.append(("🚨", lan, f"har högst andel djur som aldrig återfinns — {andel:.1f}% av länets djur klassas som 'Ej påträffat'."))

        res = _lan_topplista(filtered["Årsunge"] == "Ja")
        if res:
            lan, andel = res
            fakta.append(("🐣", lan, f"har högst andel årsungar inblandade i sina viltolyckor — {andel:.1f}%."))

        res = _lan_topplista(filtered["Europaväg"] == "Ja")
        if res:
            lan, andel = res
            fakta.append(("🛣️", lan, f"sticker ut med flest djur inblandade på europaväg — {andel:.1f}% av länets djur."))

        viltslag_counts = filtered["Viltslag"].value_counts()
        if not viltslag_counts.empty:
            sallsynt = viltslag_counts.idxmin()
            fakta.append(("🦫", sallsynt, f"är det mest sällsynta viltslaget i urvalet, med bara {viltslag_counts.min():,} registrerade djur.".replace(",", " ")))

        ar_lista = sorted(int(a) for a in filtered["År"].dropna().unique())
        if len(ar_lista) >= 2:
            forsta_ar, sista_ar = ar_lista[0], ar_lista[-1]
            sista_datum = filtered.loc[filtered["År"] == sista_ar, "Datum"].max()
            if (sista_datum.month, sista_datum.day) < (12, 25):
                sista_ar = ar_lista[-2]
            antal_forsta = filtered.loc[filtered["År"] == forsta_ar, "OlycksID_Unik"].nunique()
            antal_sista = filtered.loc[filtered["År"] == sista_ar, "OlycksID_Unik"].nunique()
            if antal_forsta > 0 and sista_ar != forsta_ar:
                forandring = (antal_sista - antal_forsta) / antal_forsta * 100
                fakta.append(("📈", f"{forandring:+.0f}%", f"har antalet viltolyckor förändrats mellan {forsta_ar} och {sista_ar} (hela kalenderår)."))

        # Vilket viltslag dominerar mest
        if not viltslag_counts.empty:
            vanligast_art = viltslag_counts.idxmax()
            andel_vanligast = viltslag_counts.max() / len(filtered) * 100
            if andel_vanligast > 50:
                fakta.append((
                    "🦌", vanligast_art,
                    f"står ensamt för {andel_vanligast:.0f}% av alla viltolyckor i urvalet — fler än alla andra viltslag tillsammans.",
                ))
            else:
                fakta.append((
                    "🦌", vanligast_art,
                    f"är det klart vanligaste viltslaget i urvalet — {andel_vanligast:.0f}% av alla djur.",
                ))

        # Vanligaste och sällsyntaste utfallet (exkl. "Olycksplats ej påträffad" som bara funnits sedan feb 2026
        # och därför alltid ser artificiellt sällsynt ut i en jämförelse över hela tidsperioden)
        utfall_counts = filtered.loc[
            filtered["Vad har skett med viltet"] != "Olycksplats ej påträffad", "Vad har skett med viltet"
        ].value_counts()
        utfall_counts = utfall_counts[utfall_counts > 0]  # kategorityp kan annars lämna kvar 0-räknade "spökkategorier"
        if len(utfall_counts) >= 2:
            totalt_utfall = utfall_counts.sum()
            vanligast_utfall = utfall_counts.idxmax()
            sallsynt_utfall = utfall_counts.idxmin()
            fakta.append((
                "☠️", vanligast_utfall,
                f"är det vanligaste utfallet för påkörda djur — {utfall_counts.max() / totalt_utfall:.0%} av alla djur, "
                f"jämfört med bara {utfall_counts.min() / totalt_utfall:.0%} för '{sallsynt_utfall}' (sällsyntast).",
            ))

        # Viltslag som sticker ut mot tåg respektive överlevnadschans (kräver rimligt stort underlag per art)
        ARTUNDERLAG_MIN = 200
        kvalificerade_arter = viltslag_counts[viltslag_counts >= ARTUNDERLAG_MIN].index
        if len(kvalificerade_arter) >= 3:
            jarnvag_per_art = {}
            oskadat_per_art = {}
            for art in kvalificerade_arter:
                sub = filtered[filtered["Viltslag"] == art]
                jarnvag_per_art[art] = (sub["Typ av olycka"] == "Järnväg").mean() * 100
                oskadat_per_art[art] = (sub["Vad har skett med viltet"] == "Bedöms oskadat").mean() * 100

            jarnvag_serie = pd.Series(jarnvag_per_art).sort_values(ascending=False)
            # Jämför mot en baslinje (3:e platsen, eller sista om färre än tre arter) istället för bara
            # tvåan - annars missas fall där TVÅ arter tillsammans sticker ut kraftigt mot resten men
            # ligger nära varandra (t.ex. björn och örn, båda extremt höga men inte 1,5x isär sinsemellan).
            baslinje_idx = min(2, len(jarnvag_serie) - 1)
            baslinje = jarnvag_serie.iloc[baslinje_idx]
            troskel = max(baslinje * 1.5, 5)
            utstickare = jarnvag_serie[jarnvag_serie > troskel]
            if len(utstickare) >= 2:
                fakta.append((
                    "🚂", f"{utstickare.index[0]} och {utstickare.index[1]}",
                    f"sticker ut kraftigt mot järnväg — {utstickare.iloc[0]:.0f}% respektive {utstickare.iloc[1]:.0f}% "
                    f"av olyckorna sker på järnväg, långt över övriga viltslag i urvalet.",
                ))
            elif len(utstickare) == 1:
                fakta.append((
                    "🚂", utstickare.index[0],
                    f"sticker ut som det viltslag som oftast krockar med tåg — {utstickare.iloc[0]:.0f}% av "
                    f"olyckorna sker på järnväg, klart mer än övriga viltslag i urvalet.",
                ))

            oskadat_serie = pd.Series(oskadat_per_art).sort_values(ascending=False)
            fakta.append((
                "💚", oskadat_serie.index[0],
                f"har högst chans att klara sig oskadd av de vanligare viltslagen — {oskadat_serie.iloc[0]:.0f}% "
                f"bedöms oskadade, jämfört med {oskadat_serie.iloc[-1]:.0f}% för {oskadat_serie.index[-1]}.",
            ))

        # Viltslag med flest årsungar inblandade
        if len(kvalificerade_arter) >= 3:
            arsunge_per_art = {}
            for art in kvalificerade_arter:
                sub = filtered[filtered["Viltslag"] == art]
                arsunge_per_art[art] = (sub["Årsunge"] == "Ja").mean() * 100
            arsunge_serie = pd.Series(arsunge_per_art).sort_values(ascending=False)
            fakta.append((
                "🐾", arsunge_serie.index[0],
                f"har högst andel årsungar inblandade av de vanligare viltslagen — {arsunge_serie.iloc[0]:.0f}% "
                f"av djuren, mot {arsunge_serie.mean():.0f}% i snitt.",
            ))

        if fakta:
            kort_delar = ['<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:0.8rem;margin-top:0.3rem;">']
            for i, (ikon, rubrik, text) in enumerate(fakta):
                farg = PALETTE[i % len(PALETTE)]
                kort_delar.append(
                    f'<div class="fact-card" style="border-left:4px solid {farg};">'
                    f'<div style="font-size:1.4rem;line-height:1;">{ikon}</div>'
                    f'<div style="font-weight:700;font-size:1rem;margin-top:0.3rem;font-family:\'Poppins\',sans-serif;">{rubrik}</div>'
                    f'<div style="font-size:0.85rem;color:#444;margin-top:0.2rem;">{text}</div>'
                    f"</div>"
                )
            kort_delar.append("</div>")
            st.markdown("".join(kort_delar), unsafe_allow_html=True)
        else:
            st.info("För få djur i urvalet för att beräkna fun facts. Justera filtren i sidopanelen.")

with tab_lokal:
    st.markdown("#### Hitta den lokala vinkeln")
    st.caption(
        "Välj ett län eller en kommun så räknar appen ut vilket mått just det området sticker ut mest på, "
        "jämfört med alla andra på samma nivå — positivt eller negativt. Tänkt som ett startskott för lokal "
        "bevakning av viltolyckor, inte en färdig slutsats."
    )

    ROVDJUR = {"Varg", "Björn", "Lo", "Järv"}
    SALLSYNTA_ARTER = ["Varg", "Björn", "Lo", "Järv", "Utter", "Mufflonfår", "Kronhjort", "Örn"]

    c1, c2 = st.columns([1, 2])
    niva_lokal = c1.radio("Nivå", ["Län", "Kommun"], horizontal=False, key="lokal_niva")
    niva_lokal_col = "Län" if niva_lokal == "Län" else "Kommun"
    niva_lokal_plural = "län" if niva_lokal == "Län" else "kommuner"
    omraden_lista = sorted(filtered[niva_lokal_col].dropna().unique())
    valt_omrade = c2.selectbox(f"Välj {niva_lokal.lower()}", omraden_lista, key="lokal_omrade")

    NATT_TIMMAR = {f"{h:02d}" for h in [22, 23, 0, 1, 2, 3, 4, 5]}

    def _omrade_matt(min_n=30):
        total = filtered.groupby(niva_lokal_col, observed=True).size()
        giltiga_index = total[total >= min_n].index
        matt = {}

        def _andel(mask, namn):
            traff = filtered[mask].groupby(niva_lokal_col, observed=True).size()
            serie = (traff / total * 100).reindex(total.index).fillna(0)
            matt[namn] = serie[serie.index.isin(giltiga_index)]

        # Utfall — alla kategorier från "Vad har skett med viltet"
        for utfall in filtered["Vad har skett med viltet"].dropna().unique():
            _andel(filtered["Vad har skett med viltet"] == utfall, f"andel med utfallet '{utfall}'")

        # Djuregenskaper och omständigheter
        _andel(filtered["Årsunge"] == "Ja", "andel årsungar")
        _andel(filtered["Europaväg"] == "Ja", "andel olyckor på europaväg")
        _andel(filtered["Typ av olycka"] == "Väg", "andel olyckor på väg (jämfört med järnväg)")
        _andel(filtered["Viltslag"].isin(ROVDJUR), "andel rovdjursolyckor (varg/björn/lo/järv)")
        _andel(filtered["TimmeVisning"].isin(NATT_TIMMAR), "andel som sker nattetid (kl 22–05)")

        # Artsammansättning — vilka viltslag är över-/underrepresenterade i området
        for art in filtered["Viltslag"].dropna().unique():
            _andel(filtered["Viltslag"] == art, f"andel {VILTSLAG_PLURAL.get(art, art.lower())}")

        matt["andel av det totala antalet djur i olyckor"] = (total / total.sum() * 100)[
            (total / total.sum() * 100).index.isin(giltiga_index)
        ]
        return matt, total

    def _troskel(n):
        return max(3, round(n * 0.05))

    def _extremitet(serie, omrade, max_andel_med_samma_varde=0.15):
        if omrade not in serie.index or len(serie) < 3:
            return None
        n = len(serie)
        varde = serie.loc[omrade]
        antal_med_samma_varde = int((serie == varde).sum())
        if antal_med_samma_varde / n > max_andel_med_samma_varde:
            return None
        rank_hog = serie.rank(ascending=False, method="min").loc[omrade]
        rank_lag = n - rank_hog + 1
        if rank_hog <= rank_lag:
            e = {"rank": int(rank_hog), "n": n, "riktning": "högst", "varde": varde, "medel": serie.mean()}
        else:
            e = {"rank": int(rank_lag), "n": n, "riktning": "lägst", "varde": varde, "medel": serie.mean()}
        return e if e["rank"] <= _troskel(n) else None

    def _riktningstext(e):
        if e["rank"] == 1:
            return e["riktning"]
        suffix = ":a" if e["rank"] % 10 in (1, 2) and e["rank"] not in (11, 12) else ":e"
        return f"{e['rank']}{suffix} {e['riktning']}"

    def _sallsynt_fakta():
        total_omraden = filtered[niva_lokal_col].nunique()
        kandidater = []
        for art in SALLSYNTA_ARTER:
            art_df = filtered[filtered["Viltslag"] == art]
            if art_df.empty or valt_omrade not in art_df[niva_lokal_col].unique():
                continue
            omraden_med_art = art_df[niva_lokal_col].nunique()
            if omraden_med_art / total_omraden < 0.5:
                antal = int((art_df[niva_lokal_col] == valt_omrade).sum())
                kandidater.append((art, omraden_med_art, total_omraden, antal))
        if not kandidater:
            return None
        return min(kandidater, key=lambda k: k[1])

    matt, total_per_omrade = _omrade_matt()
    if valt_omrade not in total_per_omrade.index or total_per_omrade.loc[valt_omrade] < 30:
        st.info(f"För få registrerade djur i {valt_omrade} inom valda filter för att räkna ut en tillförlitlig faktapunkt (minst 30 krävs).")
    else:
        resultat = []
        for namn, serie in matt.items():
            e = _extremitet(serie, valt_omrade)
            if e:
                resultat.append((namn, e))
        resultat.sort(key=lambda r: r[1]["rank"])

        if resultat:
            namn, e = resultat[0]
            st.markdown(
                f"""
                <div class="standout-card" style="border-left:4px solid #C62828;">
                    <div style="font-size:0.8rem;color:#777;text-transform:uppercase;letter-spacing:0.05em;font-weight:700;">Sticker ut mest</div>
                    <div style="font-size:1.2rem;font-weight:600;margin-top:0.3rem;font-family:'Poppins',sans-serif;">
                        {valt_omrade} har {_riktningstext(e)} {namn} av landets {e['n']} {niva_lokal_plural}
                    </div>
                    <div style="font-size:1rem;color:#333;margin-top:0.4rem;">
                        {e['varde']:.1f}% (riksgenomsnitt {e['medel']:.1f}%) — plats {e['rank']} av {e['n']}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            huvudcitat = (
                f"{valt_omrade} har {_riktningstext(e)} {namn} av landets {e['n']} {niva_lokal_plural}: "
                f"{e['varde']:.1f}% (riksgenomsnitt {e['medel']:.1f}%). {KALLA_TEXT}"
            )

            jamforelse = pd.DataFrame({
                niva_lokal_col: [valt_omrade, "Riksgenomsnitt"],
                "Värde": [e["varde"], e["medel"]],
            })
            fig_lokal = px.bar(
                jamforelse, x=niva_lokal_col, y="Värde", color=niva_lokal_col,
                labels={"Värde": namn.capitalize()}, title=f"{namn.capitalize()}: {valt_omrade} vs. riket",
                color_discrete_sequence=["#C62828", "#455A64"], text_auto=".1f",
            )
            fig_lokal.update_layout(showlegend=False)
            visa_diagram(fig_lokal)

            if len(resultat) > 1:
                st.markdown("**Andra fakta värda att nämna**")
                for namn2, e2 in resultat[1:6]:
                    st.markdown(
                        f"- {valt_omrade} har {_riktningstext(e2)} {namn2} av landets {e2['n']} {niva_lokal_plural} "
                        f"({e2['varde']:.1f}%, riksgenomsnitt {e2['medel']:.1f}%)."
                    )
        else:
            huvudcitat = None
            st.info(
                f"Inget mått sticker ut markant för {valt_omrade} med nuvarande filter — det ligger nära "
                "riksgenomsnittet på alla undersökta punkter. Testa att byta nivå (län/kommun), ett annat "
                "område, eller justera filtren i sidopanelen."
            )

        sallsynt = _sallsynt_fakta()
        if sallsynt:
            art, omraden_med_art, total_omraden, antal = sallsynt
            st.markdown(
                f"🌟 **Sällsynt:** {valt_omrade} är en av bara **{omraden_med_art} av {total_omraden}** "
                f"{niva_lokal_plural} i landet med registrerade olyckor med **{art.lower()}** "
                f"({antal:,} djur i det valda urvalet).".replace(",", " ")
            )
            sallsynt_citat = (
                f"{valt_omrade} är en av bara {omraden_med_art} av {total_omraden} {niva_lokal_plural} i landet "
                f"med registrerade olyckor med {art.lower()}. {KALLA_TEXT}"
            )
        else:
            sallsynt_citat = None

        citat_delar = [c for c in [huvudcitat, sallsynt_citat] if c]
        if citat_delar:
            st.markdown("**📋 Redo att citera**")
            st.code("\n\n".join(citat_delar), language=None)

with tab_utforska:
    st.markdown("#### Bygg ett eget diagram")
    st.caption(
        "Välj **en dimension att gruppera på** (x-axeln), och valfritt **ytterligare en dimension** att dela upp "
        "varje stapel efter (färg). För dimensioner med många olika värden (t.ex. Kommun eller Viltslag) visas "
        "bara de mest förekommande — styr hur många med reglaget. Dimensioner med en given ordning "
        "(År, Månad, Veckodag, Timme) visas alltid i sin helhet."
    )
    c1, c2, c3 = st.columns(3)
    x_label = c1.selectbox("Gruppera på (x-axel)", list(DIMENSIONS.keys()), index=0)
    color_options = ["Ingen"] + [d for d in DIMENSIONS if d != x_label]
    color_label = c2.selectbox("Dela upp/färga efter (valfritt)", color_options, index=0)
    x_ordnad = x_label in ORDNADE_DIMENSIONER_LABELS
    if x_ordnad:
        c3.caption("Alla kategorier visas eftersom **" + x_label + "** har en given ordning.")
        top_n = None
    else:
        top_n = c3.slider("Visa de N vanligaste", 3, 50, 50)
    if color_label != "Ingen":
        visa_som = st.radio(
            "Visa som", ["Antal", "Andel (%) inom varje grupp"], horizontal=True, key="utforska_visa_som"
        )
    else:
        visa_som = "Antal"

    x_col = DIMENSIONS[x_label]
    if x_ordnad:
        plot_df = filtered
        x_order = kategoriordning(x_label, [])
    else:
        top_categories = filtered[x_col].value_counts().head(top_n).index
        plot_df = filtered[filtered[x_col].isin(top_categories)]
        x_order = list(top_categories)

    if plot_df.empty:
        st.info("Inga djur matchar valda filter och val ovan.")
    else:
        if color_label == "Ingen":
            agg = plot_df.groupby(x_col, observed=True).size().reset_index(name="Antal")
            color_col = None
            cat_orders = {x_col: x_order}
        else:
            color_col = DIMENSIONS[color_label]
            agg = plot_df.groupby([x_col, color_col], observed=True).size().reset_index(name="Antal")
            color_order = kategoriordning(color_label, sorted(plot_df[color_col].dropna().unique()))
            cat_orders = {x_col: x_order, color_col: color_order}

        if visa_som != "Antal" and color_col is not None:
            totals = agg.groupby(x_col)["Antal"].transform("sum")
            agg["Andel"] = (agg["Antal"] / totals * 100).round(1)
            y_val = "Andel"
        else:
            y_val = "Antal"

        fig = px.bar(
            agg, x=x_col, y=y_val, color=color_col,
            category_orders=cat_orders, labels=LABELS,
            title=f"Antal djur per {x_label.lower()}" + (f", uppdelat på {color_label.lower()}" if color_col else ""),
            text=color_col if color_col else None,
            text_auto=True if not color_col else False,
        )
        if color_col:
            fig.update_traces(textposition="inside", insidetextfont=dict(color="white", size=12))
        visa_diagram(fig)

with tab_jamfor:
    st.markdown("#### Jämför län eller kommuner sida vid sida")
    st.caption(
        "Välj geografisk nivå och vilka län/kommuner som ska jämföras, samt vilken egenskap du vill bryta ner dem "
        "på — till exempel andelen som rapporterats som **Ej påträffat**, eller hur många som var **årsungar**."
    )
    c1, c2 = st.columns([1, 3])
    niva = c1.radio("Geografisk nivå", ["Län", "Kommun"], horizontal=False)
    niva_col = "Län" if niva == "Län" else "Kommun"
    niva_plural = "län" if niva == "Län" else "kommuner"
    niva_artikel = "ett" if niva == "Län" else "en"
    alla_omraden = filtered[niva_col].value_counts()
    forval = list(alla_omraden.head(5).index)
    valda_omraden = c2.multiselect(
        f"Välj {niva_plural} att jämföra", sorted(alla_omraden.index), default=forval
    )

    c3, c4 = st.columns(2)
    bryt_val = [l for l in DIMENSIONS if l not in ("Län", "Kommun")]
    jamfor_label = c3.selectbox(
        "Bryt ner på", bryt_val, index=bryt_val.index("Vad har skett med viltet")
    )
    visa_som_j = c4.radio("Visa som", ["Antal", "Andel (%)"], horizontal=True, key="jamfor_visa_som")

    if not valda_omraden:
        st.info(f"Välj minst {niva_artikel} {niva.lower()} ovan för att jämföra.")
    else:
        jamfor_col = DIMENSIONS[jamfor_label]
        cmp_df = filtered[filtered[niva_col].isin(valda_omraden)]
        agg = cmp_df.groupby([niva_col, jamfor_col], observed=True).size().reset_index(name="Antal")

        if visa_som_j == "Andel (%)":
            totals = agg.groupby(niva_col)["Antal"].transform("sum")
            agg["Andel"] = (agg["Antal"] / totals * 100).round(1)
            y_val, y_title = "Andel", "Andel (%)"
        else:
            y_val, y_title = "Antal", "Antal djur"

        color_order = kategoriordning(jamfor_label, sorted(agg[jamfor_col].dropna().unique()))
        fig = px.bar(
            agg, x=niva_col, y=y_val, color=jamfor_col, barmode="group",
            category_orders={jamfor_col: color_order, niva_col: valda_omraden},
            labels={**LABELS, y_val: y_title},
            title=f"{jamfor_label} per {niva.lower()}",
            text=jamfor_col,
        )
        fig.update_traces(textposition="outside", textangle=0, textfont=dict(size=11))
        fig.update_layout(uniformtext_minsize=8)
        visa_diagram(fig)

        st.markdown("**Tabell**")
        pivot = agg.pivot(index=niva_col, columns=jamfor_col, values=y_val).fillna(0)
        st.dataframe(
            pivot.style.format("{:.0f}" if visa_som_j == "Antal" else "{:.1f}"),
            width="stretch",
        )

with tab_korstabell:
    st.markdown("#### Korsa två dimensioner")
    st.caption("Se hur två valfria dimensioner hänger ihop, t.ex. Län × Viltslag eller Månad × Vad har skett med viltet.")
    c1, c2, c3 = st.columns(3)
    row_label = c1.selectbox("Rader", list(DIMENSIONS.keys()), index=0, key="row_dim")
    col_options = [d for d in DIMENSIONS if d != row_label]
    col_label = c2.selectbox("Kolumner", col_options, index=0, key="col_dim")
    top_n_cross = c3.slider("Max antal kategorier per axel", 3, 30, 30, key="top_n_cross")

    row_col = DIMENSIONS[row_label]
    col_col = DIMENSIONS[col_label]

    top_rows = (
        kategoriordning(row_label, [])
        if row_label in ORDNADE_DIMENSIONER_LABELS
        else list(filtered[row_col].value_counts().head(top_n_cross).index)
    )
    top_cols = (
        kategoriordning(col_label, [])
        if col_label in ORDNADE_DIMENSIONER_LABELS
        else list(filtered[col_col].value_counts().head(top_n_cross).index)
    )
    cross_df = filtered[filtered[row_col].isin(top_rows) & filtered[col_col].isin(top_cols)]

    if cross_df.empty:
        st.info("Inga djur matchar valda filter och val ovan.")
    else:
        cross = pd.crosstab(cross_df[row_col], cross_df[col_col])
        cross = cross.reindex(index=[c for c in top_rows if c in cross.index])
        cross = cross.reindex(columns=[c for c in top_cols if c in cross.columns])
        visa_diagram(
            px.imshow(
                cross, text_auto=True, aspect="auto", color_continuous_scale="Greens",
                labels={"x": col_label, "y": row_label, "color": "Antal djur"},
                title=f"{row_label} × {col_label}",
            ),
        )

with tab_karta:
    st.markdown("#### Karta över olycksplatser")
    st.caption(
        "Av prestandaskäl (webbläsarens minne) visas max "
        f"{MAX_MAP_POINTS:,} slumpmässigt utvalda punkter på kartan, oavsett hur många djur filtret ger.".replace(",", " ")
    )
    c1, c2 = st.columns([1, 3])
    with c1:
        map_color_label = st.selectbox("Färga punkter efter", ["Ingen"] + list(DIMENSIONS.keys()))
        map_type = st.radio("Typ av karta", ["Värmekarta", "Enskilda punkter"])

    map_df = filtered.dropna(subset=["Lat", "Long"])
    if len(map_df) > MAX_MAP_POINTS:
        c1.info(f"Visar ett slumpmässigt urval av {MAX_MAP_POINTS:,} punkter av {len(map_df):,}.".replace(",", " "))
        map_df = map_df.sample(MAX_MAP_POINTS, random_state=1)

    with c2:
        if map_df.empty:
            st.info("Inga djur med giltiga koordinater i det valda urvalet.")
        elif map_type == "Värmekarta":
            fig = px.density_map(
                map_df, lat="Lat", lon="Long", radius=4, zoom=4,
                map_style="open-street-map", height=MAP_HEIGHT, color_continuous_scale="YlOrRd",
                labels=LABELS,
            )
            visa_diagram(fig)
        else:
            color_arg = None if map_color_label == "Ingen" else DIMENSIONS[map_color_label]
            fig = px.scatter_map(
                map_df, lat="Lat", lon="Long", color=color_arg,
                zoom=4, height=MAP_HEIGHT, map_style="open-street-map", opacity=0.6,
                labels=LABELS,
            )
            visa_diagram(fig)

with tab_data:
    st.markdown("#### Filtrerad rådata")
    visning = filtered.drop(columns=["Lat", "Long", "ÅrVisning", "TimmeVisning"])
    if len(visning) > MAX_TABLE_ROWS:
        st.caption(
            f"Visar en förhandsgranskning med de {MAX_TABLE_ROWS:,} första raderna av {len(visning):,} "
            "(av prestandaskäl). Ladda ner CSV:n nedan för att få hela urvalet.".replace(",", " ")
        )
    else:
        st.caption("Tabellen visar samma urval som filtren i sidopanelen ger.")
    st.dataframe(visning.head(MAX_TABLE_ROWS), width="stretch")

    st.divider()
    if st.button("📦 Förbered CSV för nedladdning"):
        st.session_state["csv_redo"] = visning.to_csv(index=False, sep=";").encode("utf-8")

    if "csv_redo" in st.session_state:
        st.download_button(
            "⬇️ Ladda ner filtrerad data som CSV",
            st.session_state["csv_redo"],
            file_name="viltolyckor_filtrerat.csv",
            mime="text/csv",
        )
