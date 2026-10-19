import os
import random
import secrets
import string
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
import httpx

APP_DIR = Path(__file__).resolve().parent
app = FastAPI(title="LoL Spy", description="Онлайн-игра в шпиона по чемпионам League of Legends")
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

CHAMPIONS = [
    "Аатрокс", "Акали", "Акшан", "Алистар", "Амбесса", "Амуму", "Анивия",
    "Ари", "Аурелион Сол", "Афелий", "Бард", "Бел'Вет", "Блицкранк",
    "Брайер", "Браум", "Варус", "Вейн", "Вейгар", "Векс", "Вел'Коз",
    "Виего", "Виктор", "Владимир", "Вуконг", "Галио", "Гангпланк", "Гарен",
    "Гекарим", "Грагас", "Грейвз", "Гвен", "Дариус", "Джакс", "Джарван IV",
    "Джин", "Джинкс", "Доктор Мундо", "Дрейвен", "Ёнэ", "Ёрик", "Зак",
    "Зед", "Зери", "Зиггс", "Зилеан", "Зои", "Иверн", "Иллаой", "Ирелия",
    "Иезреаль", "Кай'Са", "Кайн", "Калиста", "Камилла", "Кассиопея", "Катарина",
    "Кейл", "Кейтлин", "Кеннен", "Киана", "Киндред", "Клед", "Ког'Мао",
    "Корки", "Ксин Жао", "Ле Блан", "Леона", "Ли Син", "Лилия", "Лиссандра",
    "Лулу", "Люкс", "Мальфит", "Маокай", "Мастер Йи", "Милио", "Мисс Фортуна",
    "Моргана", "Мордекайзер", "Наафири", "Нами", "Наутилус", "Нееко", "Нила",
    "Ноктюрн", "Нуну и Виллумп", "Олаф", "Орианна", "Орн", "Пайк", "Пантеон",
    "Поппи", "Райз", "Рамбл", "Раммус", "Рената Гласк", "Ренектон", "Релл",
    "Ренгар", "Ривен", "Рэйкан", "Самира", "Свейн", "Седжуани", "Сенна",
    "Серафина", "Сетт", "Сивир", "Сайлас", "Синдра", "Синджед", "Сион",
    "Скарнер", "Смолдер", "Сона", "Сорака", "Таам Кенч", "Талия", "Талон",
    "Тарик", "Твич", "Тимо", "Триндамир", "Тристана", "Трандл", "Удир",
    "Ургот", "Фай", "Фиддлстикс", "Фиора", "Физз", "Хаймердингер", "Хвэй",
    "Чо'Гат", "Шако", "Шая", "Шен", "Шивана", "Эвелинн", "Эзреаль",
    "Экко", "Элиза", "Эмбер", "Энни", "Эш", "Юми", "Ясуо", "Ярвен",
    "Ярвик", "Ясуо", "Ятэ", "Яone"
]
CHAMPIONS = list(dict.fromkeys(CHAMPIONS))
DATA_DRAGON_VERSION = None
CHAMPION_DATA = [{"id": None, "name": name, "title": "", "image": None} for name in CHAMPIONS]
SKIN_DATA = []
ITEM_DATA = []
CATEGORY_LABELS = {"champions": "Чемпионы", "skins": "Скины", "items": "Предметы"}


def champion_image_url(champion_id):
    if not champion_id:
        return None
    return f"https://ddragon.leagueoflegends.com/cdn/img/champion/splash/{champion_id}_0.jpg"


def item_image_url(item_id, version=None):
    if not item_id:
        return None
    version = version or DATA_DRAGON_VERSION or "16.18.1"
    return f"https://ddragon.leagueoflegends.com/cdn/{version}/img/item/{item_id}.png"


def clean_item_description(value):
    import re
    from html import unescape
    value = re.sub(r"<br\s*/?>", " ", value or "", flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    return " ".join(unescape(value).split())


@app.on_event("startup")
async def load_game_data():
    """Загрузить локализованные данные чемпионов, обликов и предметов из Riot Data Dragon."""
    global CHAMPION_DATA, CHAMPIONS, SKIN_DATA, ITEM_DATA, DATA_DRAGON_VERSION
    try:
        limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True, limits=limits) as client:
            versions_response = await client.get("https://ddragon.leagueoflegends.com/api/versions.json")
            versions_response.raise_for_status()
            versions = versions_response.json()
            if not versions:
                return
            version = versions[0]
            base = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/ru_RU"
            response = await client.get(f"{base}/champion.json")
            response.raise_for_status()
            raw_champions = response.json().get("data", {})
            champions = [
                {"id": item["id"], "name": item["name"], "title": item.get("title", ""),
                 "image": champion_image_url(item["id"])}
                for item in raw_champions.values() if item.get("id") and item.get("name")
            ]
            if champions:
                CHAMPION_DATA = champions
                CHAMPIONS = [item["name"] for item in champions]
                DATA_DRAGON_VERSION = version

            async def get_champion_skins(champ_id):
                try:
                    res = await client.get(f"{base}/champion/{champ_id}.json")
                    res.raise_for_status()
                    entry = res.json().get("data", {}).get(champ_id, {})
                    skins = []
                    for skin in entry.get("skins", []):
                        if skin.get("num", 0) == 0:
                            continue
                        skin_name = skin.get("name") or ""
                        if skin_name.strip().lower() in {"default", "базовый образ", "образ по умолчанию"}:
                            continue
                        skins.append({
                            "type": "skins",
                            "name": skin_name,
                            "champion": entry.get("name", champ_id),
                            "image": f"https://ddragon.leagueoflegends.com/cdn/img/champion/splash/{champ_id}_{skin['num']}.jpg",
                            "description": f"Облик чемпиона {entry.get('name', champ_id)}",
                        })
                    return skins
                except Exception as exc:
                    print(f"Не удалось загрузить облики {champ_id}: {exc}")
                    return []

            import asyncio
            skin_lists = await asyncio.gather(*(get_champion_skins(champ_id) for champ_id in raw_champions.keys()))
            loaded_skins = [skin for group in skin_lists for skin in group]
            if loaded_skins:
                SKIN_DATA = loaded_skins

            item_response = await client.get(f"{base}/item.json")
            item_response.raise_for_status()
            raw_items = item_response.json().get("data", {})
            loaded_items = []
            for item_id, item in raw_items.items():
                # Не включаем рецептурные/служебные и недоступные в обычной игре предметы.
                if not item.get("name") or not item.get("image", {}).get("full"):
                    continue
                if item.get("hideFromAll") or not item.get("inStore", True):
                    continue
                maps = item.get("maps", {})
                if maps and not maps.get("11", False):
                    continue
                description = clean_item_description(item.get("description") or item.get("plaintext") or "Описание отсутствует.")
                loaded_items.append({
                    "type": "items", "id": item_id, "name": item["name"],
                    "image": item_image_url(item_id, version),
                    "description": description or item.get("plaintext") or "Описание отсутствует.",
                    "price": item.get("gold", {}).get("total", 0),
                })
            if loaded_items:
                ITEM_DATA = loaded_items
    except Exception as exc:
        print(f"Не удалось загрузить данные из Data Dragon: {exc}. Используются резервные данные чемпионов.")

rooms = {}
players = {}
# room: {code, host_token, status, champion, spy_count, round, players:[player_id,...]}
# player: {id, room_code, name, token, role, connected}


def room_code():
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        code = "".join(secrets.choice(alphabet) for _ in range(5))
        if code not in rooms:
            return code


def room_view(room, viewer_token: Optional[str] = None):
    plist = [players[pid] for pid in room["players"] if pid in players]
    me = next((p for p in plist if p["token"] == viewer_token), None)
    personal_target = me.get("personal_target") if me else None
    my_target = personal_target if room.get("crazy_event") == "different_targets" and personal_target else room
    my_target_name = my_target.get("name") if personal_target and my_target is personal_target else my_target.get("target_name")
    my_target_image = my_target.get("image") if personal_target and my_target is personal_target else my_target.get("target_image")
    my_target_type = my_target.get("type") if personal_target and my_target is personal_target else my_target.get("target_type")
    my_target_description = my_target.get("description") if personal_target and my_target is personal_target else my_target.get("target_description")
    return {
        "code": room["code"],
        "status": room["status"],
        "round": room["round"],
        "champion": room["target_name"] if room["status"] == "finished" else None,
        "champion_image": room["target_image"] if room["status"] == "finished" else None,
        "target_type": room["target_type"] if room["status"] == "finished" else None,
        "target_description": room["target_description"] if room["status"] == "finished" else None,
        "target_category": CATEGORY_LABELS.get(room["target_type"], "") if room["status"] == "finished" else None,
        "selected_categories": room.get("selected_categories", ["champions"]),
        "crazy_mode_enabled": bool(room.get("crazy_mode_enabled", False)),
        "crazy_event_label": room.get("crazy_event_label") if room["status"] == "finished" else None,
        "spy_count": room["spy_count"],
        "players": [
            {
                "id": p["id"],
                "name": p["name"],
                "is_host": p["id"] == room["host_id"],
                "is_me": p["token"] == viewer_token,
                "role": (p["role"] if p["token"] == viewer_token and room["status"] == "playing" else None),
                "target_name": (p.get("personal_target") or {}).get("name") if room["status"] == "finished" and room.get("crazy_event") == "different_targets" else None,
            }
            for p in plist
        ],
        "is_host": bool(me and me["id"] == room["host_id"]),
        "my_role": me["role"] if me and room["status"] == "playing" else None,
        "my_champion": my_target_name if me and me["role"] == "champion" and room["status"] == "playing" else None,
        "my_champion_image": my_target_image if me and me["role"] == "champion" and room["status"] == "playing" else None,
        "my_target_type": my_target_type if me and me["role"] == "champion" and room["status"] == "playing" else None,
        "my_target_description": my_target_description if me and me["role"] == "champion" and room["status"] == "playing" else None,
        "my_target_category": CATEGORY_LABELS.get(my_target_type, "") if me and me["role"] == "champion" and room["status"] == "playing" else None,
    }


class CreateRoom(BaseModel):
    nickname: str = Field(min_length=1, max_length=20)
    spy_count: int = Field(default=1, ge=1, le=5)


class JoinRoom(BaseModel):
    nickname: str = Field(min_length=1, max_length=20)


class StartGame(BaseModel):
    token: str
    spy_count: int = Field(default=1, ge=1, le=5)
    categories: list[str] = Field(default_factory=lambda: ["champions"], min_length=1, max_length=3)
    crazy_mode: bool = False


class PlayerAction(BaseModel):
    token: str


def clean_name(name: str) -> str:
    name = " ".join(name.strip().split())
    if not name:
        raise HTTPException(400, "Введите никнейм.")
    return name[:20]


def get_room(code: str):
    room = rooms.get(code.upper())
    if not room:
        raise HTTPException(404, "Комната не найдена. Проверьте ссылку.")
    return room


def get_player(room, token: str):
    player = next((players[pid] for pid in room["players"] if pid in players and players[pid]["token"] == token), None)
    if not player:
        raise HTTPException(403, "Не удалось найти игрока. Зайдите в комнату заново.")
    return player


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={})


@app.get("/api/champions")
async def champions():
    return {
        "version": DATA_DRAGON_VERSION,
        "champions": [
            {"id": item["id"], "name": item["name"], "image": champion_image_url(item["id"])}
            for item in CHAMPION_DATA
        ],
    }


@app.get("/api/game-categories")
async def game_categories():
    return {
        "version": DATA_DRAGON_VERSION,
        "categories": [
            {"id": "champions", "name": CATEGORY_LABELS["champions"], "count": len(CHAMPION_DATA)},
            {"id": "skins", "name": CATEGORY_LABELS["skins"], "count": len(SKIN_DATA)},
            {"id": "items", "name": CATEGORY_LABELS["items"], "count": len(ITEM_DATA)},
        ],
    }


@app.post("/api/rooms")
async def create_room(data: CreateRoom):
    name = clean_name(data.nickname)
    code = room_code()
    pid = uuid.uuid4().hex
    token = secrets.token_urlsafe(24)
    room = {
        "code": code, "host_id": pid, "host_token": token, "status": "lobby",
        "champion": "", "champion_id": None, "target_name": "", "target_image": None,
        "target_type": "champions", "target_description": "", "selected_categories": ["champions"],
        "crazy_mode_enabled": False, "crazy_event": None, "crazy_event_label": None,
        "spy_count": data.spy_count, "round": 0, "players": [pid]
    }
    rooms[code] = room
    players[pid] = {"id": pid, "room_code": code, "name": name, "token": token, "role": None}
    return {"room": room_view(room, token), "token": token, "player_id": pid, "join_url": f"/room/{code}"}


@app.post("/api/rooms/{code}/join")
async def join_room(code: str, data: JoinRoom):
    room = get_room(code)
    if room["status"] != "lobby":
        raise HTTPException(400, "Игра уже началась. Создайте новую комнату или попросите ведущего начать новый раунд.")
    name = clean_name(data.nickname)
    if any(players[pid]["name"].casefold() == name.casefold() for pid in room["players"] if pid in players):
        raise HTTPException(409, "Игрок с таким никнеймом уже есть в комнате.")
    if len(room["players"]) >= 20:
        raise HTTPException(400, "В комнате максимум 20 игроков.")
    pid = uuid.uuid4().hex
    token = secrets.token_urlsafe(24)
    players[pid] = {"id": pid, "room_code": room["code"], "name": name, "token": token, "role": None}
    room["players"].append(pid)
    return {"room": room_view(room, token), "token": token, "player_id": pid}


@app.get("/api/rooms/{code}")
async def room_status(code: str, request: Request):
    room = get_room(code)
    token = request.headers.get("x-player-token", "")
    return room_view(room, token)


@app.post("/api/rooms/{code}/start")
async def start_game(code: str, data: StartGame):
    room = get_room(code)
    host = get_player(room, data.token)
    if host["id"] != room["host_id"]:
        raise HTTPException(403, "Только создатель комнаты может начать игру.")
    if room["status"] != "lobby":
        raise HTTPException(400, "Игра уже началась.")
    count = len(room["players"])
    if count < 3:
        raise HTTPException(400, "Для игры нужно минимум 3 игрока.")
    if data.spy_count >= count:
        raise HTTPException(400, "Шпионов должно быть меньше, чем игроков.")
    room["spy_count"] = data.spy_count
    allowed = {"champions", "skins", "items"}
    categories = list(dict.fromkeys(data.categories))
    if not categories or any(category not in allowed for category in categories):
        raise HTTPException(400, "Выберите хотя бы одну допустимую категорию.")
    pools = {"champions": CHAMPION_DATA, "skins": SKIN_DATA, "items": ITEM_DATA}
    pool = [dict(item, type=category) for category in categories for item in pools[category]]
    if not pool:
        raise HTTPException(503, "Для выбранных категорий не удалось загрузить данные. Проверьте подключение к Data Dragon и попробуйте снова.")
    target = random.choice(pool)
    room["target_type"] = target["type"]
    room["target_name"] = target["name"]
    room["target_image"] = target.get("image")
    room["target_description"] = target.get("description", "")
    room["selected_categories"] = categories
    room["champion"] = target["name"]
    room["champion_id"] = target.get("id")
    room["crazy_mode_enabled"] = data.crazy_mode
    room["crazy_event"] = None
    room["crazy_event_label"] = None
    for pid in room["players"]:
        players[pid].pop("personal_target", None)

    # Crazy mode: only 20% of enabled rounds activate a chaos scenario.
    crazy_scenarios = []
    if data.crazy_mode and random.random() < 0.20:
        count = len(room["players"])
        extra_spy_counts = [n for n in (2, 3) if n < count and n != data.spy_count]
        if extra_spy_counts:
            crazy_scenarios.append("extra_spies")
        if count - 1 != data.spy_count and count - 1 not in extra_spy_counts:
            crazy_scenarios.append("solo_spy")
        crazy_scenarios.append("different_targets")
        event = random.choice(crazy_scenarios)
        room["crazy_event"] = event

        if event == "different_targets":
            # Everyone is told they are not a spy, but each gets a different object.
            targets = random.sample(pool, count) if len(pool) >= count else [random.choice(pool) for _ in room["players"]]
            for pid, personal_target in zip(room["players"], targets):
                players[pid]["role"] = "champion"
                players[pid]["personal_target"] = personal_target
            room["target_type"] = target["type"]
            room["target_name"] = target["name"]
            room["target_image"] = target.get("image")
            room["target_description"] = target.get("description", "")
            room["crazy_event_label"] = "Хаос: у каждого игрока был свой объект"
        else:
            actual_spy_count = random.choice(extra_spy_counts) if event == "extra_spies" else count - 1
            chosen = set(random.sample(room["players"], actual_spy_count))
            for pid in room["players"]:
                players[pid]["role"] = "spy" if pid in chosen else "champion"
            room["spy_count"] = actual_spy_count
            room["crazy_event_label"] = (
                f"Хаос: вместо ожидаемого количества было {actual_spy_count} шпионов"
                if event == "extra_spies" else
                "Хаос: все игроки, кроме одного, оказались шпионами"
            )
    else:
        chosen = set(random.sample(room["players"], data.spy_count))
        for pid in room["players"]:
            players[pid]["role"] = "spy" if pid in chosen else "champion"
    room["round"] += 1
    room["status"] = "playing"
    return room_view(room, data.token)


@app.post("/api/rooms/{code}/reveal")
async def reveal_champion(code: str, data: PlayerAction):
    room = get_room(code)
    player = get_player(room, data.token)
    if player["id"] != room["host_id"]:
        raise HTTPException(403, "Только создатель комнаты может завершить раунд.")
    if room["status"] != "playing":
        raise HTTPException(400, "Сейчас нет активной игры.")
    room["status"] = "finished"
    return room_view(room, data.token)


@app.post("/api/rooms/{code}/reset")
async def reset_room(code: str, data: PlayerAction):
    room = get_room(code)
    player = get_player(room, data.token)
    if player["id"] != room["host_id"]:
        raise HTTPException(403, "Только создатель комнаты может начать новый раунд.")
    room["status"] = "lobby"
    room["champion"] = ""
    room["champion_id"] = None
    room["target_name"] = ""
    room["target_image"] = None
    room["target_description"] = ""
    room["target_type"] = "champions"
    room["target_description"] = ""
    room["crazy_event"] = None
    room["crazy_event_label"] = None
    for pid in room["players"]:
        if pid in players:
            players[pid]["role"] = None
            players[pid].pop("personal_target", None)
    return room_view(room, data.token)


@app.post("/api/rooms/{code}/leave")
async def leave_room(code: str, data: PlayerAction):
    room = get_room(code)
    player = get_player(room, data.token)
    pid = player["id"]
    room["players"] = [p for p in room["players"] if p != pid]
    players.pop(pid, None)
    if not room["players"]:
        rooms.pop(room["code"], None)
        return {"ok": True, "room_deleted": True}
    if room["host_id"] == pid:
        room["host_id"] = room["players"][0]
        room["host_token"] = players[room["host_id"]]["token"]
    if room["status"] == "playing":
        room["status"] = "lobby"
        room["champion"] = ""
        room["target_name"] = ""
        room["target_image"] = None
        room["target_description"] = ""
        room["target_type"] = "champions"
        room["target_description"] = ""
        room["crazy_event"] = None
        room["crazy_event_label"] = None
        for p in room["players"]:
            players[p]["role"] = None
            players[p].pop("personal_target", None)
    return {"ok": True, "room_deleted": False}


@app.get("/room/{code}", response_class=HTMLResponse)
async def room_page(request: Request, code: str):
    return templates.TemplateResponse(request=request, name="index.html", context={"room_code": code.upper()})


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/health")
async def health():
    return {"status": "ok"}
