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
