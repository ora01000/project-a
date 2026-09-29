# Inventory SQL skill

에이전트가 인벤토리(SQLite) 데이터를 조회할 때 따르는 스킬이다.  
**스키마를 먼저 확인하고**, 질의 문맥에 맞는 **읽기 전용 SQL**을 만든 뒤, 결과로 사용자에게 답한다.

## 사용 가능한 도구 (MCP)

| 도구 | 용도 | 필수 파라미터 |
|------|------|----------------|
| `getInventoryList` | 등록된 인벤토리 테이블 목록 | 없음 |
| `getInventorySchema` | 특정 인벤토리 테이블 컬럼/타입 스키마 | `inventory` (테이블명) |
| `readDataUsingSQL` | 읽기 전용 SQL 실행 후 결과 조회 | `sql` (SELECT 문) |

- 스키마·목록은 **반드시 위 MCP 도구**로 읽는다. 추측으로 테이블/컬럼명을 만들지 않는다.
- `readDataUsingSQL`에는 **SELECT(또는 WITH … SELECT)만** 보낸다. INSERT/UPDATE/DELETE/DROP/ATTACH 등 변경·DDL은 금지한다.

---

## 작업 순서 (MUST)

1. **`getInventoryList`**  
   - 어떤 `table_name` / `display_name` / `description`이 있는지 확인한다.  
   - 사용자 질의의 주제(자산, 서버, 호스트 등)와 `display_name`·`description`·`table_name`을 매칭해 **대상 테이블을 고른다**.  
   - 후보가 여러 개면 가장 관련 있는 1개(필요 시 2개)만 고르고, 왜 골랐는지 답변에 짧게 밝힌다.

2. **`getInventorySchema`**  
   - 선택한 테이블에 대해 `inventory=<table_name>`으로 호출한다.  
   - 응답의 `columns[].name`, `columns[].type`을 기준으로 컬럼을 고른다.  
   - 스키마에 없는 컬럼명은 SQL에 쓰지 않는다.

3. **SQL 생성** (아래 「SQLite SQL 생성 가이드」)

4. **`readDataUsingSQL`** 로 실행

5. **결과로 질의에 답변**  
   - 행이 있으면 핵심 컬럼을 표·목록으로 정리한다.  
   - 0행이면 “조건에 맞는 행 없음”을 말하고, 가능하면 조건을 완화한 재조회(LIKE 확대, OR 추가)를 한 번 시도한다.  
   - SQL 오류가 나면 스키마를 다시 확인하고 쿼리를 수정한 뒤 재실행한다.

임시 테이블(`temp_…`)은 사용자 질의 대상이 **아닐 때** 제외한다. 목록에 `inventory_`로 시작하는 정식 테이블을 우선한다.

---

## SQLite SQL 생성 가이드

### 1. 기본 원칙

- 방언: **SQLite**.
- 테이블명은 스키마/목록에 나온 값을 **그대로** 쓴다. (보통 `inventory_…`)
- 식별자에 예약어·특수문자가 있으면 `"column_name"`처럼 큰따옴표로 감싼다. 일반 `snake_case` TEXT 컬럼은 따옴표 없이 써도 된다.
- 문자열 리터럴은 **작은따옴표** `'…'`. 값 안의 `'`는 `''`로 이스케이프한다.
- 기본 형태:

```sql
SELECT column_a, column_b, …
FROM inventory_example
WHERE …
ORDER BY …
LIMIT 50;
```

- 결과가 많을 수 있으면 **`LIMIT`을 둔다** (기본 50, 사용자가 더 원하면 증가). 집계·존재 여부만 필요하면 `COUNT(*)` / `LIMIT 1`을 쓴다.

### 2. 컬럼 ↔ 질의 키 매칭

스키마 컬럼명과 사용자 말의 의미를 대응시킨다. 예:

| 사용자 표현 예 | 후보 컬럼 예 (스키마에 있을 때) |
|----------------|----------------------------------|
| 자산 ID, Asset ID, SRV-001 | `asset_id` |
| 호스트, 서버 이름, hostname | `hostname` |
| IP, 아이피 | `ip_address` |
| OS, 운영체제 | `os` |
| 환경, prod/dev | `environment` |
| 위치, AZ, region | `location` |
| 상태, Active | `status` |
| 담당, 소유자 | `owner` |

- 애매하면 **관련 가능성이 높은 여러 컬럼을 `OR`로** 묶는다.  
- 스키마에 없는 이름은 사용하지 않는다. “비슷한 이름”으로 임의 생성하지 않는다.

### 3. 부분 문자열 검색 — `LIKE '%키%'` (중요)

사용자 질의의 값은 **전체 셀 값과 일치하지 않는 경우가 많다** (일부 hostname, ID 일부, IP 일부 등).  
정확도를 높이려면 동등(`=`)보다 **부분 일치**를 기본으로 한다.

```sql
-- 권장: 부분 일치
WHERE asset_id LIKE '%SRV-001%'

-- 비권장(값이 완전 일치할 때만)
WHERE asset_id = 'SRV-001'
```

규칙:

1. 사용자가 준 검색어 `키`에 대해 `LIKE '%키%'` 형태를 쓴다.  
2. 대소문자: SQLite 기본 `LIKE`는 ASCII에서 대소문자 무시인 경우가 많다. 한글·특수문자는 스키마/데이터 그대로 맞춘다.  
3. 여러 키워드가 있으면:
   - **모두 만족**해야 하면 `AND`
   - **하나만 맞아도** 되면 `OR`
4. 같은 키를 여러 후보 컬럼에 칠 때:

```sql
WHERE (
     hostname LIKE '%web-prod%'
  OR asset_id LIKE '%web-prod%'
  OR ip_address LIKE '%web-prod%'
)
```

5. `LIKE` 패턴에서 사용자 입력의 `%` / `_` 는 와일드카드가 되지 않게, 가능하면 제거하거나 이스케이프한다. (불명확하면 해당 문자를 뺀 키로 검색)

### 4. 조건 조합 예시

**예: “SRV-001 자산 정보”** (스키마에 `asset_id`, `hostname` 등이 있을 때)

```sql
SELECT asset_id, hostname, ip_address, os, environment, status, owner
FROM inventory_asset
WHERE asset_id LIKE '%SRV-001%'
   OR hostname LIKE '%SRV-001%'
LIMIT 50;
```

**예: “서울 prod 웹 서버”**

```sql
SELECT asset_id, hostname, ip_address, environment, location, status
FROM inventory_asset
WHERE environment LIKE '%prod%'
  AND (
       hostname LIKE '%web%'
    OR asset_id LIKE '%web%'
  )
  AND location LIKE '%Seoul%'
LIMIT 50;
```

**예: “10.0.1 대역 IP”**

```sql
SELECT asset_id, hostname, ip_address, status
FROM inventory_asset
WHERE ip_address LIKE '%10.0.1%'
LIMIT 50;
```

**예: 건수만**

```sql
SELECT COUNT(*) AS cnt
FROM inventory_asset
WHERE status LIKE '%Active%';
```

### 5. SELECT 절

- 사용자가 특정 필드만 물으면 해당 컬럼 + 식별에 필요한 키(`asset_id`, `hostname` 등)를 함께 고른다.
- “전부 / 상세”면 스키마의 주요 컬럼을 나열한다. `SELECT *`는 허용하되, 가능하면 명시 컬럼이 낫다.
- 존재하지 않는 컬럼을 SELECT하지 않는다.

### 6. 읽기 전용 · 안전

`readDataUsingSQL`에 넣기 전 스스로 검사한다.

- 허용: `SELECT`, `WITH … SELECT`
- 금지: `INSERT`, `UPDATE`, `DELETE`, `REPLACE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, `ATTACH`, `DETACH`, `PRAGMA`로 쓰는 변경, 다중 스테이트먼트(`;`)로 쓰기 문 결합
- `LIMIT` 없는 광역 `SELECT * FROM big_table`은 피하고 항상 `LIMIT`을 둔다.

### 7. 생성 체크리스트

- [ ] `getInventoryList`로 테이블을 골랐는가?  
- [ ] `getInventorySchema`로 컬럼을 확인했는가?  
- [ ] SQL의 테이블·컬럼명이 스키마와  Exact match 인가?  
- [ ] 사용자 키값에 `LIKE '%…%'`를 적용했는가?  
- [ ] 읽기 전용 SELECT이며 `LIMIT`이 있는가?  
- [ ] 문자열 이스케이프(`'` → `''`)를 했는가?

---

## SQL 수행 후 답변

1. `readDataUsingSQL` 결과의 행·컬럼을 바탕으로 **사용자 언어로** 요약한다.  
2. 원본 SQL은 짧게 인용하거나 “조회 조건”으로 풀어 설명한다.  
3. 행이 많으면 상위 N개만 보여 주고 전체 건수를 알린다.  
4. 데이터가 없거나 모호하면:
   - 사용한 테이블/조건을 밝히고  
   - 추가 식별 정보(정확한 hostname, IP, asset_id 등)를 요청한다.

### 금지

- 스키마를 보지 않고 SQL을 먼저 실행하기  
- 목록에 없는 테이블명 가정  
- 쓰기 SQL 또는 다중 문장 실행  
- 결과와 무관한 추측성 인벤토리 단정
