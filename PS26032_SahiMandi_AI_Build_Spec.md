# PS26032 Build Specification

> **Purpose:** Full build specification for the PS26032 solution.  
> **Audience:** A team of five or six with moderate coding experience and no machine learning background.


**Problem Statement:** SIH26032, Ministry of Consumer Affairs, Food & Public Distribution, Department of Consumer Affairs
**Category:** Software | **Theme:** Smart Automation | **Deadline:** 20 September 2026
**Title:** Farmers often face long waiting times, lack of information regarding procurement schedules, and uncertainty about procurement status.

**Expected solution as published by the ministry:**
1. Enables farmer registration and slot booking
2. Provides real-time queue management
3. Sends SMS/app notifications
4. Tracks procurement and payment status
5. Reduces congestion and waiting time at procurement centres

This document is the full build spec. It assumes a team of five or six with moderate coding experience and no machine learning background.

---

## 1. Positioning

Every team attempting this PS will build registration, slot booking, SMS and a status page. Those five bullets are table stakes, not differentiation. Building them well is necessary and not sufficient.

**The differentiator, in one sentence:**

> Most slot booking systems calculate capacity from how fast the weighing counter runs. Ours calculates it from whatever is actually limiting the centre that day, which is usually gunny bags, hamalis or lorries, so the date a farmer is given is a date the centre can keep. When a centre is choked, the system stops issuing slots there and redirects the farmer to the nearest centre with real capacity.

**Why this is the right differentiator:**

Farmers do not wait because the weighing counter is slow. In most seasons the counter is idle. The centre stalls because gunny bags ran out, hamalis are unavailable, or the contractor lorry has not returned from the mill. A booking system that promises a slot the centre cannot honour is worse than no booking system, because the farmer now arrives on a fixed date with harvested grain and nowhere to put it.

**What this protects against:** the question "how is this different from MP e-Uparjan or the state procurement portals". Without the capacity engine there is no answer to that question.

---

## 2. Scope

### In scope
- Farmer self registration and slot booking
- Deterministic capacity engine with the four constraint inputs
- Centre officer console for daily inputs and lot state updates
- Live queue board with estimated wait
- Six state lot lifecycle with immutable event log
- Notification service, mocked gateway for demo
- Choked centre detection and redirect to nearest alternative
- District officer dashboard
- Simulation module for the demo

### Out of scope, and say so openly
- Real payment disbursement. The system mirrors payment state entered by the procurement clerk. It does not move money and does not integrate with PFMS or state treasury.
- Automated quality grading from images. Grading is entered by the officer.
- USSD shortcodes. These need a telecom aggregator agreement and cannot be built or demoed in a hackathon. SMS gateway only, mocked for the demo.
- Live GPS truck tracking. Truck availability is a number the officer enters.
- Any LLM or generative model. The PS theme is Smart Automation and the entire system is deterministic arithmetic.

Stating these clearly in the deck is a strength. Judges penalise teams that claim treasury integration and cannot show it.

---

## 3. Users and roles

| Role | Who | Access |
|---|---|---|
| Farmer | Registers, books slot, sees queue and status | Own lots only |
| Centre Officer | Staff at a procurement centre | Own centre, all lots at that centre |
| District Officer | Supervises multiple centres | Read only across centres, plus capacity overrides |
| Admin | Team, for the demo | Everything, plus simulation controls |

Authentication for the prototype: phone number plus OTP for farmers, with the OTP printed to the mock notification panel. Username and password for officers. Do not build real SMS OTP for the demo.

---

## 4. The capacity engine

This is the core of the system. Everything else is CRUD around it.

### 4.1 Inputs, entered by the centre officer each morning

| Input | Symbol | Example |
|---|---|---|
| Counters open | `counters` | 2 |
| Quintals processed per counter per hour | `rate_per_counter` | 25 |
| Operating hours today | `hours` | 8 |
| Gunny bags in stock | `bags_available` | 3000 |
| Quintals per bag | `qtl_per_bag` | 0.4 |
| Hamalis on duty | `hamalis` | 6 |
| Quintals a hamali handles per day | `rate_per_hamali` | 90 |
| Yard buffer capacity in quintals | `buffer_capacity` | 2500 |
| Unlifted stock at open | `stock_open` | 1800 |
| Trucks assigned today | `trucks` | 2 |
| Trips per truck per day | `trips_per_truck` | 1 |
| Quintals per truck load | `qtl_per_truck` | 250 |

Defaults are seeded per centre so the officer only edits what changed. Realistic defaults matter for the demo.

### 4.2 The four constraints

```
staff_cap    = counters * rate_per_counter * hours
bag_cap      = bags_available * qtl_per_bag
hamali_cap   = hamalis * rate_per_hamali
lift_today   = trucks * trips_per_truck * qtl_per_truck
yard_cap     = (buffer_capacity - stock_open) + lift_today

daily_capacity = min(staff_cap, bag_cap, hamali_cap, yard_cap)
binding_constraint = name of whichever term produced the minimum
```

`yard_cap` is the term that carries the real world insight. If the yard is nearly full and no truck is coming, the centre cannot accept grain regardless of how fast the counter runs.

Worked example with the values above:

```
staff_cap  = 2 * 25 * 8            = 400 qtl
bag_cap    = 3000 * 0.4            = 1200 qtl
hamali_cap = 6 * 90                = 540 qtl
lift_today = 2 * 1 * 250           = 500 qtl
yard_cap   = (2500 - 1800) + 500   = 1200 qtl

daily_capacity = 400, binding = STAFF
```

Now drop the trucks to zero and raise opening stock to 2400:

```
yard_cap = (2500 - 2400) + 0 = 100 qtl
daily_capacity = 100, binding = YARD
```

The centre can still weigh 400 quintals and has 1200 quintals of bags, but it can only accept 100. That gap is the entire pitch.

### 4.3 Choked state

```
choked = (binding_constraint != "STAFF") AND (daily_capacity < 0.5 * staff_cap)
```

A choked centre stops accepting new bookings for that date and every booking attempt returns the redirect list instead.

### 4.4 Overbooking for no shows

Farmers miss slots. Transport breaks down, harvest runs late. Booking exactly to capacity wastes it.

```
no_show_rate    = rolling share of bookings in the last 14 days that never checked in,
                  floor 0.05, ceiling 0.30, default 0.15 for a centre with no history
bookable_qtl    = min(daily_capacity / (1 - no_show_rate), 1.25 * daily_capacity)
```

The 1.25 ceiling stops a bad no show estimate from creating the exact congestion the system exists to prevent. State this ceiling in the deck. It shows the team thought about failure, which scores.

### 4.5 Slot allocation

- The operating day is divided into hourly buckets.
- Each bucket gets `bookable_qtl / hours` quintals of allowance.
- A farmer booking `q` quintals is placed in the earliest bucket on the requested date with at least `q` remaining, using first fit. This is simple, explainable and deterministic.
- If no bucket on that date fits, offer the next date, then the redirect list.

### 4.6 Missed slots

- Grace period of 60 minutes past slot start.
- After grace, the booking moves to `STANDBY` and the allowance is released back to the bucket.
- Standby lots are served in FIFO order whenever a bucket has unused allowance at the end of an hour.
- A farmer on standby is never pushed behind a later booked farmer who has not yet arrived.

This is the answer to the "what if a farmer misses their slot" question, and it is answered without complex reallocation logic.

---

## 5. Lot lifecycle

A lot is one farmer's delivery. It moves through six states, forward only.

```
REGISTERED -> ARRIVED -> WEIGHED -> GRADED -> LIFTED -> SETTLED
```

| State | Set by | Meaning | SMS sent |
|---|---|---|---|
| REGISTERED | System, on booking | Slot confirmed | Yes, slot details |
| ARRIVED | Officer, at gate | Token issued, in queue | Yes, token and position |
| WEIGHED | Officer | Weight recorded | Yes, weight and lot id |
| GRADED | Officer | Moisture and grade recorded, deductions applied | Yes, grade and net quintals |
| LIFTED | Officer | Loaded on lorry to mill | Yes, truck and mill |
| SETTLED | Clerk | Payment marked released | Yes, amount and reference |

Rules:
- No state is ever edited or deleted. Corrections are new events with a `correction_of` reference.
- Every transition writes one row into `lot_events` with actor, timestamp and payload.
- Every transition enqueues one notification.

The status page for the farmer is just a render of that event list. Nothing extra to build.

---

## 6. Data model

PostgreSQL. Nine tables. Keep it at nine.

```sql
farmers
  id              bigserial pk
  phone           varchar(15) unique not null
  name            varchar(120) not null
  village         varchar(120)
  district        varchar(120)
  land_acres      numeric(6,2)
  created_at      timestamptz default now()

centres
  id              bigserial pk
  name            varchar(160) not null
  district        varchar(120) not null
  latitude        numeric(9,6)
  longitude       numeric(9,6)
  open_hour       int default 9
  close_hour      int default 17
  buffer_capacity numeric(10,2)
  active          boolean default true

centre_users
  id              bigserial pk
  centre_id       bigint fk -> centres
  username        varchar(60) unique
  password_hash   text
  role            varchar(20)   -- OFFICER | CLERK | DISTRICT

centre_daily_capacity
  id                  bigserial pk
  centre_id           bigint fk -> centres
  for_date            date not null
  counters            int
  rate_per_counter    numeric(8,2)
  hours               int
  bags_available      int
  qtl_per_bag         numeric(5,2) default 0.4
  hamalis             int
  rate_per_hamali     numeric(8,2)
  stock_open          numeric(10,2)
  trucks              int
  trips_per_truck     int default 1
  qtl_per_truck       numeric(8,2) default 250
  daily_capacity      numeric(10,2)   -- computed, stored
  binding_constraint  varchar(12)     -- STAFF | BAGS | HAMALI | YARD
  choked              boolean
  unique (centre_id, for_date)

slots
  id              bigserial pk
  centre_id       bigint fk -> centres
  for_date        date not null
  hour            int not null
  allowance_qtl   numeric(10,2)
  booked_qtl      numeric(10,2) default 0
  unique (centre_id, for_date, hour)

lots
  id              bigserial pk
  farmer_id       bigint fk -> farmers
  centre_id       bigint fk -> centres
  slot_id         bigint fk -> slots null
  crop            varchar(40)
  declared_qtl    numeric(8,2)
  gross_qtl       numeric(8,2) null
  net_qtl         numeric(8,2) null
  grade           varchar(10) null
  moisture_pct    numeric(5,2) null
  amount_due      numeric(12,2) null
  token_no        int null
  state           varchar(12) default 'REGISTERED'
  standby         boolean default false
  created_at      timestamptz default now()

lot_events
  id              bigserial pk
  lot_id          bigint fk -> lots
  from_state      varchar(12)
  to_state        varchar(12)
  actor_type      varchar(12)     -- SYSTEM | OFFICER | CLERK
  actor_id        bigint null
  payload         jsonb
  correction_of   bigint null fk -> lot_events
  created_at      timestamptz default now()

notifications
  id              bigserial pk
  lot_id          bigint fk -> lots null
  phone           varchar(15)
  body            text
  channel         varchar(10) default 'SMS'
  status          varchar(10) default 'QUEUED'  -- QUEUED | SENT | FAILED
  created_at      timestamptz default now()
  sent_at         timestamptz null

service_times
  id              bigserial pk
  centre_id       bigint fk -> centres
  lot_id          bigint fk -> lots
  arrived_at      timestamptz
  weighed_at      timestamptz
  minutes         numeric(8,2)
```

`lot_events` and `notifications` are append only by convention. Add a trigger blocking UPDATE and DELETE on `lot_events` if there is time. It is four lines of SQL and it is a good thing to show a judge.

---

## 7. API surface

FastAPI. Roughly twenty endpoints.

**Public and farmer**
```
POST   /auth/otp/request           {phone}
POST   /auth/otp/verify            {phone, code} -> token
POST   /farmers                    register
GET    /centres/nearby             ?lat=&lng=&date=&qtl=
GET    /centres/{id}/availability   ?date=&qtl=
POST   /bookings                   {centre_id, date, crop, declared_qtl}
GET    /bookings/mine
DELETE /bookings/{lot_id}          cancel, releases allowance
GET    /lots/{id}/status           lot + full event timeline
GET    /centres/{id}/queue         live board, public
```

**Centre officer**
```
POST   /officer/capacity           daily inputs, returns computed capacity + binding constraint
GET    /officer/queue              today's lots at this centre
POST   /officer/lots/{id}/arrive   issues token
POST   /officer/lots/{id}/weigh    {gross_qtl}
POST   /officer/lots/{id}/grade    {grade, moisture_pct, net_qtl, amount_due}
POST   /officer/lots/{id}/lift     {truck_no, mill}
POST   /officer/lots/{id}/settle   {reference, amount}   CLERK role
POST   /officer/lots/{id}/correct  {event_id, payload}
```

**District and admin**
```
GET    /district/overview          all centres, capacity, choked flags, backlog
GET    /district/centre/{id}       drilldown
POST   /sim/run                    {days, policy} -> run id
GET    /sim/{run_id}/results       series for the charts
GET    /dev/notifications          the mock SMS inbox for the demo panel
```

Every state transition endpoint does three things in one transaction: write the lot state, write the `lot_events` row, enqueue the notification. Write that as a single helper function and call it from all six. Do not duplicate the logic six times.

---

## 8. Screens

**Farmer, mobile first, three screens**
1. Register and login
2. Book a slot. Pick crop, quintals, district. The centre list shows for each option: next available date, distance, and a status chip reading Open, Filling or Choked. A choked centre is shown greyed with the reason in plain language, for example "Trucks unavailable, backlog 2400 quintals".
3. My lots. Timeline of the six states with timestamps, plus live queue position when in ARRIVED state.

**Centre officer, desktop, two screens**
1. Morning capacity form. On submit it shows the four computed numbers side by side with the binding one highlighted, and the resulting bookable quintals. This screen is the demo centrepiece.
2. Queue console. Today's lots in order with one action button each, following the lifecycle.

**District officer, one screen**
Table of centres with capacity, binding constraint, backlog, choked flag. A choked centre is red. Sortable by backlog.

**Demo panel**
A phone shaped panel showing the mock SMS inbox, live. Cheap to build, and it makes the notification bullet visible in five seconds during the pitch.

**Design note:** the officer console will be used by a clerk on a low end machine with poor light. Large type, high contrast, no more than one action per row. Say this out loud in the pitch. Judges notice when a team has thought about who actually operates the software.

---

## 9. Notification service

- Every state change inserts a row into `notifications` with `status = QUEUED`.
- A background worker polls queued rows every few seconds, calls the gateway adapter, marks `SENT`.
- The gateway adapter is an interface with two implementations: `MockGateway` writes to the demo panel, `Msg91Gateway` or `TwilioGateway` makes a real HTTP call.
- Demo runs with the mock. The real adapter exists and is shown in the code walkthrough.

Message templates, kept under 160 characters and bilingual English plus regional:

```
BOOKED   Slot confirmed. {centre}, {date} {hour}:00. Lot {lot_id}. Bring {qtl} qtl.
ARRIVED  Token {token}. {ahead} ahead of you. Approx wait {wait} min. Lot {lot_id}.
WEIGHED  Weight recorded {gross} qtl. Lot {lot_id}.
GRADED   Grade {grade}, moisture {moisture}%. Net {net} qtl. Amount {amount}. Lot {lot_id}.
LIFTED   Your lot has left for {mill}. Lot {lot_id}.
SETTLED  Payment released. Amount {amount}. Ref {reference}. Lot {lot_id}.
CHOKED   {centre} cannot accept grain on {date}. Nearest open centre {alt} on {alt_date}.
```

The CHOKED message is the one that saves a farmer a wasted trip. Point at it in the pitch.

---

## 10. Queue wait estimation

No model. An exponentially weighted moving average.

```
On every WEIGHED event, compute minutes from ARRIVED to WEIGHED, store in service_times.
ewma_new = 0.3 * latest_minutes + 0.7 * ewma_previous
Seed ewma at 12 minutes for a centre with no history.

estimated_wait_minutes = (lots ahead in queue) * ewma / counters_open
```

Three lines, explainable to a judge in one sentence, and accurate enough. Do not reach for a regression model here. It adds nothing and invites questions about training data you do not have.

---

## 11. Simulation module

This is the highest value item in the build and it is what the judges will remember.

**What it does:** replays a season at one centre under two policies and charts the difference.

**Inputs**
- 30 days of synthetic farmer arrivals, weighted to a realistic harvest curve, that is low, rising to a peak around days 10 to 18, then tailing off
- Daily truck availability with random shortfalls, for example 20 percent of days have zero trucks
- Gunny bag deliveries in batches with occasional gaps

**Policy A, baseline:** farmers walk in whenever they like. The centre accepts until the yard is full, then everyone waits.

**Policy B, this system:** bookings capped at `bookable_qtl`, choked days redirect a share of farmers to a second centre.

**Outputs, two line charts**
1. Queue length by day, A versus B
2. Average farmer wait in hours, A versus B

Plus three headline numbers: peak queue reduced by X percent, average wait reduced by Y hours, farmers redirected before travelling Z.

**Implementation:** a plain Python script under `sim/`, writing results to a table, with the frontend reading them. No simulation framework needed. A loop over 30 days with the capacity engine called each day is enough. Reuse the real capacity function so the simulation is testing the actual code, not a copy. Say that out loud, because it is true and it is good engineering.

---

## 12. Stack and repository layout

```
Frontend   React 18 + Vite, plain CSS or Tailwind, Recharts for the two charts
Backend    FastAPI, SQLAlchemy, Pydantic
Database   PostgreSQL 16
Worker     A background thread in FastAPI for the notification queue. Do not add Celery or Redis.
```

No Docker, no Kubernetes, no microservices, no message broker, no blockchain, no ML. If a judge asks why not, the answer is that a single centre serves a few hundred farmers a day and this runs comfortably on one small server, and every added component is another thing that breaks during the demo.

```
SahiMandi/
  backend/
    app/
      main.py
      models.py
      schemas.py
      capacity.py        <- the engine, keep it isolated and unit tested
      lifecycle.py       <- the single state transition helper
      notify.py
      routers/
        auth.py  farmers.py  bookings.py  officer.py  district.py  sim.py
    tests/
      test_capacity.py   <- most important test file in the repo
    seed.py
    requirements.txt
  frontend/
    src/
      pages/  components/  api.js
    package.json
  sim/
    run_simulation.py
  README.md
```

`capacity.py` should be a pure function with no database calls. It takes the inputs, returns the four numbers, the minimum, and the binding constraint name. That makes it trivially testable and it lets the simulation reuse it. This one decision is worth more than any framework choice.

---

## 13. Setup, Windows PowerShell

```powershell
# Backend
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install fastapi uvicorn "sqlalchemy>=2.0" psycopg2-binary pydantic python-dotenv passlib
python seed.py
uvicorn app.main:app --reload --port 8000

# Frontend, in a second terminal
cd frontend
npm install
npm run dev

# Simulation
cd backend
.\.venv\Scripts\Activate.ps1
python ..\sim\run_simulation.py --days 30 --centre 1
```

If PowerShell blocks the venv activation script:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

PostgreSQL connection string in `backend/.env`:

```
DATABASE_URL=postgresql+psycopg2://postgres:password@localhost:5432/ps26032
```

---

## 14. Build order

Numbered so the team knows what to cut when time runs out. Items 1 to 7 are a complete, submittable system. Items 8 to 10 are what make it place.

| # | Item | Depends on | Rough effort |
|---|---|---|---|
| 1 | Schema, models, seed data for 4 centres and 60 farmers | none | 1 day |
| 2 | `capacity.py` plus its unit tests | 1 | half day |
| 3 | Officer capacity form and queue console | 1, 2 | 1.5 days |
| 4 | Lifecycle helper and the six transition endpoints | 1 | 1 day |
| 5 | Farmer registration, booking, availability | 2, 3 | 1.5 days |
| 6 | Notifications, mock gateway, demo panel | 4 | half day |
| 7 | Farmer status timeline and live queue board | 4, 6 | 1 day |
| 8 | Choked detection and nearby centre redirect | 2, 5 | 1 day |
| 9 | Simulation and the two charts | 2 | 1.5 days |
| 10 | District dashboard | 3, 8 | 1 day |

Build order note: item 3 comes before item 5 deliberately. The officer console is the source of all data in the system. Without it there is nothing for the farmer app to display, so building the farmer app first leaves the team with pretty screens and no content.

### Team split for six people

| Person | Owns |
|---|---|
| 1 | Schema, seed data, capacity engine, tests |
| 2 | Officer console, both screens |
| 3 | Farmer app, registration and booking |
| 4 | Farmer app, status timeline and queue board |
| 5 | Lifecycle endpoints, notifications, mock gateway |
| 6 | Simulation, charts, district dashboard, and the deck |

Person 6 owning both the simulation and the deck is intentional. The simulation produces the numbers the deck argues from, so the same person should hold both.

---

## 15. Demo script, five minutes

1. **Fifteen seconds.** The claim. Farmers wait days at procurement centres. Most of that wait is not the weighing counter being slow. It is bags, hamalis and lorries. Existing slot systems do not model any of those.
2. **Forty five seconds.** Officer capacity screen. Enter a normal day. Four numbers appear, staff is the smallest, capacity 400 quintals. Now set trucks to zero and opening stock to 2400. Capacity collapses to 100 and the screen turns red with the binding constraint reading YARD. State plainly: the counter can still do 400, the centre can only accept 100.
3. **Forty five seconds.** Farmer app. Attempt to book at that centre. It is greyed with a plain language reason and the app offers the nearest open centre instead. The SMS panel shows the CHOKED message arriving. This is the trip that did not get wasted.
4. **Ninety seconds.** Full lifecycle on one lot. Arrive, weigh, grade, lift, settle. After each click, show the farmer timeline updating and the SMS landing in the panel. This clears four of the five ministry bullets in ninety seconds without narrating them.
5. **Sixty seconds.** Simulation. Two charts. Peak queue and average wait, baseline versus this system. Read the three headline numbers.
6. **Thirty seconds.** What is deliberately not built and why. Payment is mirrored, not disbursed. Grading is by the officer, not by image. No USSD. Ending on honest limits reads as maturity, not weakness.

Rehearse this at least four times. A demo that stalls at minute two loses more marks than any missing feature.

---

## 16. Judge questions and answers

**How is this different from MP e-Uparjan?**
Those systems allocate slots from a fixed daily quota set administratively. Ours computes the quota each morning from the four physical constraints and refuses bookings when the constraint is not the counter. The redirect on choked centres does not exist in those systems.

**Why not use AI to predict arrivals?**
The theme is Smart Automation and the bottleneck is capacity accounting, not prediction. Everything here is arithmetic the officer can verify by hand, which matters because a centre officer has to trust the number before acting on it. A forecasting model is a reasonable phase two once a season of real data exists.

**What if the officer enters wrong capacity inputs?**
Every entry is timestamped and attributed in the event log, and the district dashboard shows centres whose entered capacity diverges from their actual processed volume. Bad entries are visible, not silent.

**What if farmers do not have smartphones?**
Nothing in the critical path requires one. Bookings can be made by a centre operator or a common service centre on the farmer's behalf, and every state change goes out over SMS to a basic handset.

**What if a farmer misses their slot?**
Sixty minute grace, then standby with FIFO service in unused capacity. Their allowance returns to the pool. No cascading delay for anyone else.

**Does overbooking not recreate the congestion you are solving?**
It is capped at 1.25 times real capacity and driven by the centre's own measured no show rate over 14 days. The ceiling is the safeguard.

**Where does truck availability data come from?**
The officer enters it each morning, the same way they already track it on paper. Integration with the transport contractor's system is a natural phase two but it is not required for the system to work.

**Can this scale to a state?**
One centre handles a few hundred lots a day. The computation is a minimum of four numbers per centre per day. A single Postgres instance handles a full state comfortably.

---

## 17. Known weaknesses

State these in the deck rather than waiting to be caught on them.

1. Capacity inputs depend on honest officer entry. Mitigated by the audit log and divergence flags, not eliminated.
2. Redirect only helps where a second centre is reachable. In sparse districts it degrades to an accurate warning, which still saves a wasted trip.
3. Payment state is only as fresh as the clerk's entry. Without treasury integration this is a ceiling on the fourth ministry bullet, and no team can clear that ceiling in a hackathon.
4. No show rate needs history. The first two weeks at any centre run on the default of 0.15.
