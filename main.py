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
    "Иซриал", "Кай'Са", "Кайн", "Калиста", "Камилла", "Кассиопея", "Катарина",
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
# Remove duplicate entries while preserving order.
CHAMPIONS = list(dict.fromkeys(CHAMPIONS))

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
    return {
        "code": room["code"],
        "status": room["status"],
        "round": room["round"],
        "champion": room["champion"] if room["status"] == "finished" else None,
        "spy_count": room["spy_count"],
        "players": [
            {
                "id": p["id"],
                "name": p["name"],
                "is_host": p["id"] == room["host_id"],
                "is_me": p["token"] == viewer_token,
                "role": (p["role"] if p["token"] == viewer_token and room["status"] == "playing" else None),
            }
            for p in plist
        ],
        "is_host": bool(me and me["id"] == room["host_id"]),
        "my_role": me["role"] if me and room["status"] == "playing" else None,
        "my_champion": (
            room["champion"]
            if me and me["role"] != "spy" and room["status"] == "playing"
            else None
        ),
    }


class CreateRoom(BaseModel):
    nickname: str = Field(min_length=1, max_length=20)
    spy_count: int = Field(default=1, ge=1, le=5)


class JoinRoom(BaseModel):
    nickname: str = Field(min_length=1, max_length=20)


class StartGame(BaseModel):
    token: str
    spy_count: int = Field(default=1, ge=1, le=5)


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
    return templates.TemplateResponse(
    request=request,
    name="index.html",
    context={}
)


@app.get("/api/champions")
async def champions():
    return {"champions": CHAMPIONS}


@app.post("/api/rooms")
async def create_room(data: CreateRoom):
    name = clean_name(data.nickname)
    code = room_code()
    pid = uuid.uuid4().hex
    token = secrets.token_urlsafe(24)
    room = {
        "code": code, "host_id": pid, "host_token": token, "status": "lobby",
        "champion": "", "spy_count": data.spy_count, "round": 0, "players": [pid]
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
    room["champion"] = random.choice(CHAMPIONS)
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
    for pid in room["players"]:
        if pid in players:
            players[pid]["role"] = None
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
        for p in room["players"]:
            players[p]["role"] = None
    return {"ok": True, "room_deleted": False}


@app.get("/room/{code}", response_class=HTMLResponse)
async def room_page(request: Request, code: str):
    return templates.TemplateResponse(
    request=request,
    name="index.html",
    context={"room_code": code.upper()}
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/health")
async def health():
    return {"status": "ok"}
