# SpacePulse demo timetables

Fictional data for **Demo University Mode**. Neither file describes a real college timetable.

| File | Role |
|---|---|
| `Timetable_A_Initial.csv` | Loaded and activated by `manage.py seed_spacepulse_demo` (regular semester schedule) |
| `Timetable_B_Updated.csv` | Not loaded. Faculty upload it from the app (SpacePulse → Manage Timetables) during the demo |

Timetable B, compared with A:
- **Now occupied:** Monday 11:00–12:00 in ECE-101 (Microcontrollers) and CSE-301 (AI Workshop).
- **Now free:** Monday 15:00–16:00 in ECE-102 (Signals and Systems is dropped).
- **Activity changed:** Friday 11:00–12:00 in IT-201 (Machine Learning → Deep Learning).

## CSV format

UTF-8 text, one header row, one class per row. Each row is a **weekly** class: the room is taken every such
weekday between `start` and `end` (campus local time, `DJANGO_TIME_ZONE`, default Asia/Kolkata).

```
day,start,end,room_id,activity
Monday,09:00,10:00,ECE-101,Digital Electronics
```

| Column | Rules |
|---|---|
| `day` | Monday … Sunday (or Mon … Sun), any case |
| `start`, `end` | `HH:MM` 24-hour (`9:00`, `14:30`, or `2:30 PM` also work); end after start; between 06:00 and 22:00 |
| `room_id` | An existing room ID, e.g. `ECE-101` (admin → Rooms) |
| `activity` | Up to 120 characters |

Columns may be in any order. `room`, `classroom`, `subject` and `weekday` are accepted as alternative names.
One room can't hold two overlapping classes on the same day. If any row is invalid, the whole file is
rejected and every problem is listed with its line number; nothing is saved.

## Demo classrooms (fictional capacities)

| Room | Name | Seats |
|---|---|---:|
| ECE-101 | Electronics Classroom 101 | 30 |
| ECE-102 | Electronics Classroom 102 | 45 |
| IT-201 | Information Technology Room 201 | 60 |
| CSE-301 | Computer Science Room 301 | 75 |
| SEM-01 | Seminar Room 01 | 100 |
| HALL-01 | Conference Hall 01 | 150 |
