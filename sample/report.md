# Report

The guide says "Always run the migration script before restarting the service" (src/guide.md:3).

It also warns that "the cache will hold stale schema entries for up to ten minutes" (src/guide.md:9).

The doc notes "safe mode disables the HTTP API" (src/guide.md:8).

> The "safe mode" flag disables background workers [...] it does not disable the HTTP API.

한국어 메모는 "캐시는 최대 10분 동안 이전 스키마를 유지할 수있다"라고 적는다 (src/notes_ko.txt:2).

The guide claims "never restart without a backup"[^1].

[^1]: src/guide.md

Finally, "Always run the migration script after restarting the service" (src/guide.md:3).
