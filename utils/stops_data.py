"""
utils/stops_data.py — All 38 New Year Train stops + schedule generation.

UTC offset logic:
  fire_utc = datetime(year, 1, 1, 0, 0, UTC) - timedelta(minutes=offset_mins)

  UTC+8  (Singapore) → Dec 31 16:00 UTC
  UTC±0  (London)    → Jan 1  00:00 UTC
  UTC-12 (Baker Is.) → Jan 1  12:00 UTC
"""

from datetime import datetime, timedelta, timezone
from utils.db import get_conn, upsert_scheduled_job, jobs_exist_for_year, get_all_stops

STOPS_RAW = [
    (1,  840, "UTC +14",    "🕙", "- Line Islands (Kiribati) 🇰🇮"),
    (2,  825, "UTC +13:45", "🕥", "- Chatham Islands (New Zealand) 🇳🇿"),
    (3,  780, "UTC +13",    "🕚",
        "- Auckland (New Zealand) 🇳🇿\n- Samoa 🇼🇸\n- Tokelau 🇹🇰\n- Tonga 🇹🇴\n- Kanton Island (Kiribati) 🇰🇮"),
    (4,  720, "UTC +12",    "🕛",
        "- Fiji 🇫🇯\n- Tarawa (Kiribati) 🇰🇮\n- Marshall Islands 🇲🇭\n- Nauru 🇳🇷\n- Norfolk Island 🇳🇫\n"
        "- Petropavlovsk-Kamchatsky (Russia) 🇷🇺\n- Tuvalu 🇹🇻\n- Wake Island (U.S. Minor Outlying Islands) 🇺🇲\n"
        "- Wallis and Futuna 🇼🇫"),
    (5,  660, "UTC +11",    "🕐",
        "- Sydney (Australia) 🇦🇺\n- Tofol (Micronesia) 🇫🇲\n- New Caledonia 🇳🇨\n"
        "- Yuzhno-Sakhalinsk (Russia) 🇷🇺\n- Solomon Islands 🇸🇧\n- Vanuatu 🇻🇺\n- Arawa (Papua New Guinea) 🇵🇬"),
    (6,  630, "UTC +10:30", "🕧", "- Adelaide (Australia) 🇦🇺"),
    (7,  600, "UTC +10",    "🕑",
        "- Brisbane (Australia) 🇦🇺\n- Guam 🇬🇺\n- Weno (Micronesia) 🇫🇲\n- North Mariana Islands 🇲🇵\n"
        "- Port Moresby (Papua New Guinea) 🇵🇬\n- Vladivostok (Russia) 🇷🇺"),
    (8,  570, "UTC +9:30",  "🕝", "- Darwin (Australia) 🇦🇺"),
    (9,  540, "UTC +9",     "🕒",
        "- Manokwari (Indonesia) 🇮🇩\n- Japan 🇯🇵\n- North Korea 🇰🇵\n- Chita (Russia) 🇷🇺\n"
        "- Timor-Leste 🇹🇱\n- South Korea 🇰🇷"),
    (10, 525, "UTC +8:45",  "🕞", "- Eucla (Australia) 🇦🇺"),
    (11, 480, "UTC +8",     "🕓",
        "- Perth (Australia) 🇦🇺\n- Brunei 🇧🇳\n- China 🇨🇳\n- Hong Kong 🇭🇰\n- Nusantara (Indonesia) 🇮🇩\n"
        "- Macau 🇲🇴\n- Malaysia 🇲🇾\n- Choibalsan (Mongolia) 🇲🇳\n- Philippines 🇵🇭\n"
        "- Irkutsk (Russia) 🇷🇺\n- Singapore 🇸🇬\n- Taiwan 🇹🇼"),
    (12, 420, "UTC +7",     "🕔",
        "- Cambodia 🇰🇭\n- Christmas Island 🇨🇽\n- Jakarta (Indonesia) 🇮🇩\n- Laos 🇱🇦\n"
        "- Hovd (Mongolia) 🇲🇳\n- Novosibirsk (Russia) 🇷🇺\n- Thailand 🇹🇭\n- Vietnam 🇻🇳"),
    (13, 390, "UTC +6:30",  "🕠", "- Cocos Islands 🇨🇨\n- Myanmar 🇲🇲"),
    (14, 360, "UTC +6",     "🕕",
        "- Bangladesh 🇧🇩\n- Bhutan 🇧🇹\n- British Indian Ocean Territory 🇮🇴\n"
        "- Kyrgyzstan 🇰🇬\n- Omsk (Russia) 🇷🇺"),
    (15, 345, "UTC +5:45",  "🕡", "- Nepal 🇳🇵"),
    (16, 330, "UTC +5:30",  "🕡", "- India 🇮🇳\n- Sri Lanka 🇱🇰"),
    (17, 300, "UTC +5",     "🕖",
        "- Port-aux-Français (France) 🇫🇷\n- Kazakhstan 🇰🇿\n- Maldives 🇲🇻\n- Pakistan 🇵🇰\n"
        "- Yekaterinburg (Russia) 🇷🇺\n- Tajikistan 🇹🇯\n- Turkmenistan 🇹🇲\n- Uzbekistan 🇺🇿"),
    (18, 270, "UTC +4:30",  "🕢", "- Afghanistan 🇦🇫"),
    (19, 240, "UTC +4",     "🕗",
        "- Armenia 🇦🇲\n- Azerbaijan 🇦🇿\n- Tbilisi (Georgia) 🇬🇪\n- Mauritius 🇲🇺\n- Oman 🇴🇲\n"
        "- Samara (Russia) 🇷🇺\n- Réunion 🇷🇪\n- Seychelles 🇸🇨\n- United Arab Emirates 🇦🇪"),
    (20, 210, "UTC +3:30",  "🕣", "- Iran 🇮🇷"),
    (21, 180, "UTC +3",     "🕘",
        "- Bahrain 🇧🇭\n- Belarus 🇧🇾\n- Comoros 🇰🇲\n- Djibouti 🇩🇯\n- Eritrea 🇪🇷\n- Ethiopia 🇪🇹\n"
        "- Sukhumi (Georgia) 🇬🇪\n- Iraq 🇮🇶\n- Jordan 🇯🇴\n- Kenya 🇰🇪\n- Kuwait 🇰🇼\n"
        "- Madagascar 🇲🇬\n- Mayotte 🇾🇹\n- Qatar 🇶🇦\n- Moscow (Russia) 🇷🇺\n- Saudi Arabia 🇸🇦\n"
        "- Somalia 🇸🇴\n- Prince Edward Islands (South Africa) 🇿🇦\n- Syria 🇸🇾\n- Tanzania 🇹🇿\n"
        "- Türkiye 🇹🇷\n- Uganda 🇺🇬\n- Donetsk (Ukraine) 🇺🇦\n- Yemen 🇾🇪"),
    (22, 120, "UTC +2",     "🕙",
        "- Botswana 🇧🇼\n- Bulgaria 🇧🇬\n- Burundi 🇧🇮\n- Lubumbashi (Congo Democratic Republic) 🇨🇩\n"
        "- Cyprus 🇨🇾\n- Egypt 🇪🇬\n- Estonia 🇪🇪\n- Eswatini 🇸🇿\n- Finland 🇫🇮\n- Greece 🇬🇷\n"
        "- Israel 🇮🇱\n- Latvia 🇱🇻\n- Lebanon 🇱🇧\n- Lesotho 🇱🇸\n- Libya 🇱🇾\n- Lithuania 🇱🇹\n"
        "- Malawi 🇲🇼\n- Moldova 🇲🇩\n- Mozambique 🇲🇿\n- Namibia 🇳🇦\n- Palestine 🇵🇸\n"
        "- Romania 🇷🇴\n- Kaliningrad (Russia) 🇷🇺\n- Rwanda 🇷🇼\n- Johannesburg (South Africa) 🇿🇦\n"
        "- South Sudan 🇸🇸\n- Sudan 🇸🇩\n- Kyiv (Ukraine) 🇺🇦\n- Zambia 🇿🇲\n- Zimbabwe 🇿🇼\n- Åland Islands 🇦🇽"),
    (23,  60, "UTC +1",     "🕚",
        "- Albania 🇦🇱\n- Algeria 🇩🇿\n- Andorra 🇦🇩\n- Angola 🇦🇴\n- Austria 🇦🇹\n- Belgium 🇧🇪\n"
        "- Benin 🇧🇯\n- Bosnia and Herzegovina 🇧🇦\n- Cameroon 🇨🇲\n- Central African Republic 🇨🇫\n"
        "- Chad 🇹🇩\n- Congo-Brazzaville 🇨🇬\n- Kinshasa (Congo Democratic Republic) 🇨🇩\n"
        "- Croatia 🇭🇷\n- Czechia 🇨🇿\n- Denmark 🇩🇰\n- Equatorial Guinea 🇬🇶\n- Paris (France) 🇫🇷\n"
        "- Gabon 🇬🇦\n- Germany 🇩🇪\n- Gibraltar 🇬🇮\n- Hungary 🇭🇺\n- Italy 🇮🇹\n- Kosovo 🇽🇰\n"
        "- Liechtenstein 🇱🇮\n- Luxembourg 🇱🇺\n- Malta 🇲🇹\n- Monaco 🇲🇨\n- Montenegro 🇲🇪\n"
        "- Morocco 🇲🇦\n- Amsterdam (Netherlands) 🇳🇱\n- Niger 🇳🇪\n- Nigeria 🇳🇬\n"
        "- North Macedonia 🇲🇰\n- Norway 🇳🇴\n- Poland 🇵🇱\n- San Marino 🇸🇲\n- Serbia 🇷🇸\n"
        "- Slovakia 🇸🇰\n- Slovenia 🇸🇮\n- Madrid (Spain) 🇪🇸\n- Sweden 🇸🇪\n- Switzerland 🇨🇭\n"
        "- Tunisia 🇹🇳\n- Vatican City 🇻🇦\n- Western Sahara 🇪🇭"),
    (24,   0, "UTC ±0",     "🕛",
        "- Burkina Faso 🇧🇫\n- Canary Islands 🇮🇨\n- Faroe Islands 🇫🇴\n- Ghana 🇬🇭\n"
        "- Danmarkshavn (Greenland) 🇬🇱\n- Guernsey 🇬🇬\n- Isle of Man 🇮🇲\n- Jersey 🇯🇪\n"
        "- Guinea 🇬🇳\n- Guinea-Bissau 🇬🇼\n- Iceland 🇮🇸\n- Ireland 🇮🇪\n- Ivory Coast 🇨🇮\n"
        "- Liberia 🇱🇷\n- Mali 🇲🇱\n- Mauritania 🇲🇷\n- Lisbon (Portugal) 🇵🇹\n- Saint Helena 🇸🇭\n"
        "- Senegal 🇸🇳\n- Sierra Leone 🇸🇱\n- Las Palmas (Spain) 🇪🇸\n- São Tomé and Príncipe 🇸🇹\n"
        "- Gambia 🇬🇲\n- Togo 🇹🇬\n- United Kingdom 🇬🇧"),
    (25,  -60, "UTC -1",    "🕐", "- Ponta Delgada (Portugal) 🇵🇹\n- Cabo Verde 🇨🇻"),
    (26, -120, "UTC -2",    "🕑",
        "- Fernando de Noronha (Brazil) 🇧🇷\n- South Georgia and the South Sandwich Islands 🇬🇸\n"
        "- Nuuk (Greenland) 🇬🇱"),
    (27, -180, "UTC -3",    "🕒",
        "- Argentina 🇦🇷\n- São Paulo (Brazil) 🇧🇷\n- Santiago (Chile) 🇨🇱\n- Falkland Islands 🇫🇰\n"
        "- French Guiana 🇬🇫\n- Paraguay 🇵🇾\n- Saint Pierre and Miquelon 🇵🇲\n- Suriname 🇸🇷\n- Uruguay 🇺🇾"),
    (28, -210, "UTC -3:30", "🕞", "- Newfoundland, St. John's (Canada) 🇨🇦"),
    (29, -240, "UTC -4",    "🕓",
        "- Anguilla 🇦🇮\n- Antigua and Barbuda 🇦🇬\n- Aruba 🇦🇼\n- Barbados 🇧🇧\n- Bermuda 🇧🇲\n"
        "- Bolivia 🇧🇴\n- Manaus (Brazil) 🇧🇷\n- British Virgin Islands 🇻🇬\n- Halifax (Canada) 🇨🇦\n"
        "- Caribbean Netherlands 🇧🇶\n- Curaçao 🇨🇼\n- Dominica 🇩🇲\n- Dominican Republic 🇩🇴\n"
        "- Thule Air Base (Greenland) 🇬🇱\n- Grenada 🇬🇩\n- Guadeloupe 🇬🇵\n- Guyana 🇬🇾\n"
        "- Martinique 🇲🇶\n- Montserrat 🇲🇸\n- Puerto Rico 🇵🇷\n- Saint Barthélemy 🇧🇱\n"
        "- Saint Lucia 🇱🇨\n- Saint Martin 🇲🇫\n- Saint Kitts and Nevis 🇰🇳\n"
        "- Saint Vincent and the Grenadines 🇻🇨\n- Trinidad and Tobago 🇹🇹\n- U.S. Virgin Islands 🇻🇮\n"
        "- Venezuela 🇻🇪"),
    (30, -300, "UTC -5",    "🕔",
        "- Rio Branco (Brazil) 🇧🇷\n- Toronto (Canada) 🇨🇦\n- Cayman Islands 🇰🇾\n"
        "- Easter Island (Chile) 🇨🇱\n- Colombia 🇨🇴\n- Cuba 🇨🇺\n- Quito (Ecuador) 🇪🇨\n"
        "- Cancún (Mexico) 🇲🇽\n- Panama 🇵🇦\n- Peru 🇵🇪\n- The Bahamas 🇧🇸\n"
        "- Turks and Caicos Islands 🇹🇨\n"
        "- Florida, Michigan, Tennessee [EST], New York, Pennsylvania, Georgia, North Carolina (United States) 🇺🇸"),
    (31, -360, "UTC -6",    "🕕",
        "- Belize 🇧🇿\n- Winnipeg (Canada) 🇨🇦\n- Costa Rica 🇨🇷\n- Galapagos Islands (Ecuador) 🇪🇨\n"
        "- El Salvador 🇸🇻\n- Guatemala 🇬🇹\n- Honduras 🇭🇳\n- Mexico City (Mexico) 🇲🇽\n"
        "- Nicaragua 🇳🇮\n- Texas, Michigan, Florida, Tennessee [CST], Illinois, Ohio (United States) 🇺🇸"),
    (32, -420, "UTC -7",    "🕖",
        "- British Columbia [MST], Edmonton (Canada) 🇨🇦\n- Hermosillo (Mexico) 🇲🇽\n"
        "- Oregon, Texas, Nevada [MST], Arizona, Colorado, Utah (United States) 🇺🇸"),
    (33, -480, "UTC -8",    "🕗",
        "- British Columbia [PST], Vancouver (Canada) 🇨🇦\n- Tijuana (Mexico) 🇲🇽\n"
        "- Pitcairn Islands 🇵🇳\n- Oregon, Idaho, Nevada [PST], California, Washington (United States) 🇺🇸"),
    (34, -540, "UTC -9",    "🕘",
        "- Gambier Islands (French Polynesia) 🇵🇫\n- Alaska [AKST] (United States) 🇺🇸"),
    (35, -570, "UTC -9:30", "🕤", "- Taiohae (French Polynesia) 🇵🇫"),
    (36, -600, "UTC -10",   "🕙",
        "- Cook Islands 🇨🇰\n- Papeete (French Polynesia) 🇵🇫\n"
        "- Alaska [HST], Hawaii (United States) 🇺🇸\n- Johnston Atoll (U.S. Minor Outlying Islands) 🇺🇸"),
    (37, -660, "UTC -11",   "🕚",
        "- American Samoa 🇦🇸\n- Niue 🇳🇺\n- Midway (U.S. Minor Outlying Islands) 🇺🇸"),
    (38, -720, "UTC -12",   "🕛", "- Baker Island (U.S. Minor Outlying Islands) 🇺🇸"),
]


def _ordinal(n: int) -> str:
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    return f"{n}{['th','st','nd','rd','th'][min(n % 10, 4)]}"


def seed_stops():
    with get_conn() as conn:
        for stop_num, offset_mins, label, emoji, locs in STOPS_RAW:
            conn.execute(
                """INSERT OR REPLACE INTO train_stops
                   (stop_number, utc_offset_mins, stop_label, clock_emoji, locations_text)
                   VALUES (?, ?, ?, ?, ?)""",
                (stop_num, offset_mins, label, emoji, locs)
            )


def compute_fire_utc(year: int, offset_mins: int) -> datetime:
    return datetime(year, 1, 1, 0, 0, 0, tzinfo=timezone.utc) - timedelta(minutes=offset_mins)


def build_schedule_for_year(year: int, force: bool = False):
    if jobs_exist_for_year(year) and not force:
        return
    stops = get_all_stops()
    first_fire = compute_fire_utc(year, stops[0]["utc_offset_mins"])
    last_fire  = compute_fire_utc(year, stops[-1]["utc_offset_mins"])
    upsert_scheduled_job(year, "pre_train",  (first_fire - timedelta(minutes=5)).isoformat(), None)
    for stop in stops:
        fire = compute_fire_utc(year, stop["utc_offset_mins"])
        upsert_scheduled_job(year, f"stop_{stop['stop_number']}", fire.isoformat(), stop["stop_number"])
    upsert_scheduled_job(year, "post_train", (last_fire + timedelta(minutes=5)).isoformat(), None)
    print(f"[stops_data] Built schedule for {year}.")


# ---------------------------------------------------------------------------
# Message formatters
# ---------------------------------------------------------------------------

def _format_utc_time(fire_dt: datetime) -> tuple[str, str]:
    h, m = fire_dt.hour, fire_dt.minute
    if m == 0:
        if h == 0:    time_str = "12 MN"
        elif h == 12: time_str = "12 NN"
        elif h < 12:  time_str = f"{h} AM"
        else:         time_str = f"{h - 12} PM"
    else:
        disp = h if h <= 12 else h - 12
        if disp == 0: disp = 12
        time_str = f"{disp}:{m:02d} {'AM' if h < 12 else 'PM'}"
    date_label = "December 31" if fire_dt.month == 12 else "January 1"
    return time_str, date_label


def format_pre_train_message(year: int) -> str:
    return (
        f"-=-=-=-\n"
        f"The New Years' {year} Train will be arriving at the first stop in an hour! 🥳\n"
        f"Fasten your seat belts and enjoy the ride!\n"
        f"-=-=-=-"
    )


def format_stop_message(stop_number: int, stop_label: str, clock_emoji: str,
                        locations_text: str, year: int, offset_mins: int) -> str:
    fire_dt = compute_fire_utc(year, offset_mins)
    time_str, date_label = _format_utc_time(fire_dt)
    ordinal = _ordinal(stop_number)
    return (
        f"\n# 🎉 {ordinal} stop: **{stop_label}**\n"
        f"## {clock_emoji} Current UTC time: {time_str} ({date_label})\n\n"
        f"### 📣 Happy New Year to those who live in:\n"
        f"{locations_text}"
    )


def format_post_train_message(year: int) -> str:
    return (
        f"-=-=-=-\n"
        f"The New Year Train has arrived at the terminal station.\n"
        f"Thank you for taking the train, and we will see you again next year.\n\n"
        f"Don't forget to take all of your bags, snacks and belongings! 🥳\n"
        f"-=-=-=-"
    )