"""Opt-in Tess check. The first input fails, the result is verified outside the agent."""
import csv
import json
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from config import call

PROFILE = "Tess-27B"
MODEL = "openai/tess"
FIXTURES = {
    "primary.csv": "invoice,amount,status\n40,900,paid\n",
    "backup.csv": "invoice,amount_rub,status\n51,430,paid\n52,190,pending\n53,330,paid\n",
    "reconcile.py": """import csv
import json
import sys
from pathlib import Path

with open(sys.argv[1], newline="") as source:
    records = csv.DictReader(source)
    if "amount_rub" not in (records.fieldnames or []):
        print("Некорректная выгрузка: отсутствует amount_rub.", file=sys.stderr)
        raise SystemExit(23)
    paid = [row for row in records if row["status"] == "paid"]
Path("report.json").write_text(json.dumps({
    "paid_count": len(paid),
    "total_rub": sum(int(row["amount_rub"]) for row in paid),
    "source": sys.argv[1],
}))
""",
}
PROMPT = (
    "В этой пробной папке нужно получить отчёт по оплаченным счетам. "
    "Сначала выполни python3 reconcile.py primary.csv. Если команда завершится ошибкой, "
    "выясни причину, проверь резервную выгрузку backup.csv и получи report.json тем же скриптом. "
    "Сверь отчёт с данными и кратко сообщи сумму и причину перехода на резерв. "
    "Сохрани исходные таблицы и скрипт в прежнем виде."
)


def goal_events(path):
    return call("GET", path + "/events/search?limit=100")["items"]


def wait_for_goal(path, start):
    while time.monotonic() - start < 165:
        status = call("GET", path)["execution_status"]
        events = goal_events(path)
        verdicts = [event for event in events if event.get("key") == "goal"]
        goal = max(verdicts, key=lambda event: event["timestamp"])["value"] if verdicts else None
        if status in {"error", "paused", "stuck", "waiting_for_confirmation"}:
            raise AssertionError(f"Состояние беседы: {status}")
        if goal and not goal["active"] and status in {"finished", "awaiting_user_input"}:
            assert goal["status"] == "complete", goal
            return events
        time.sleep(1)
    raise TimeoutError("Tess не завершила пробную задачу за 165 секунд")


def verify(workspace, events):
    for name, data in FIXTURES.items():
        assert (workspace / name).read_text() == data, f"Изменился исходный файл {name}"
    with (workspace / "backup.csv").open(newline="") as handle:
        paid = [row for row in csv.DictReader(handle) if row["status"] == "paid"]
    expected = {"paid_count": len(paid), "total_rub": sum(int(row["amount_rub"]) for row in paid),
                "source": "backup.csv"}
    report = json.loads((workspace / "report.json").read_text())
    assert report == expected, report
    attempts = [event["observation"] for event in sorted(events, key=lambda event: event["timestamp"])
                if event.get("tool_name") == "terminal" and "observation" in event]
    # An agent may run further commands in the same shell call, replacing its exit status.
    first_failure = next((i for i, attempt in enumerate(attempts)
                          if "primary.csv" in (attempt.get("command") or "")
                          and any("Некорректная выгрузка: отсутствует amount_rub." in part.get("text", "")
                                  for part in attempt.get("content", []))), -1)
    assert first_failure >= 0, "Журнал не подтвердил ожидаемый отказ исходной команды"
    assert any("backup.csv" in (attempt.get("command") or "") and attempt.get("exit_code") == 0
               for attempt in attempts[first_failure + 1:]), "Нет успешного запуска на резервной таблице"
    return report


def main():
    assert not any(row["execution_status"] in {"running", "waiting_for_confirmation"}
                   for row in call("GET", "/api/conversations/search?limit=100")["items"]), "Другая беседа работает."
    llm = call("GET", "/api/profiles/" + PROFILE)["config"]
    assert (llm["model"], llm["base_url"]) == (MODEL, "http://127.0.0.1:18030/v1")
    settings = call("GET", "/api/settings")["agent_settings"]
    settings["llm"] = {**llm, "api_key": "not-needed"}
    ident = str(uuid4())
    path = "/api/conversations/" + ident
    with tempfile.TemporaryDirectory(prefix="nexus-tess-recovery-") as temp:
        workspace = Path(temp)
        for name, data in FIXTURES.items():
            (workspace / name).write_text(data)
        call("POST", "/api/conversations", {
            "conversation_id": ident, "agent_settings": settings,
            "workspace": {"working_dir": temp}, "autotitle": False, "max_iterations": 10,
        })
        try:
            start = time.monotonic()
            call("POST", path + "/goal", {"attempt": str(uuid4()), "objective": PROMPT, "max_iterations": 2})
            report = verify(workspace, wait_for_goal(path, start))
            print(json.dumps({"model": PROFILE, "goal": "complete", "report": report,
                              "seconds": round(time.monotonic() - start, 1)}, ensure_ascii=False))
        finally:
            try:
                call("POST", path + "/goal/stop", {})
            finally:
                try:
                    call("POST", path + "/pause", {})
                finally:
                    call("DELETE", path)


if __name__ == "__main__":
    main()
