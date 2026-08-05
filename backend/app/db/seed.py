from typing import TypedDict


class SeedUser(TypedDict):
    userid: str
    email: str
    username: str
    password: str
    depart: str
    role: int
    band: int


INITIAL_USERS: list[SeedUser] = [
    {
        "userid": "root",
        "email": "isyun@lguplus.co.kr",
        "username": "관리자",
        "password": "root-internal-bypass-only",
        "depart": "IT플랫폼운영팀",
        "role": 100,
        "band": 3,
    },
    {
        "userid": "isyun",
        "email": "isyun@lguplus.co.kr",
        "username": "윤인수",
        "password": "isyun",
        "depart": "IT플랫폼운영팀",
        "role": 0,
        "band": 3,
    },
    {
        "userid": "loadan",
        "email": "loadan@lguplus.co.kr",
        "username": "안세훈",
        "password": "loadan",
        "depart": "IT플랫폼운영팀",
        "role": 0,
        "band": 3,
    },
]
