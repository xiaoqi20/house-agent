"""运行隔离（契约 §2.1 / 选型 §8）：并发运行、取消互不影响、旧 run 不污染新会话。

后台 run 与请求共享事件循环，这里用可等待的慢回答把两条运行真正并发起来，
断言 done.result 只落在自己的会话/事件流上。
"""

import asyncio

from rentgraph.services import engine
from tests.conftest import collect_events, create_conversation, wait_run


def _install_slow_answer(monkeypatch, delay: float = 0.3, only: str | None = None) -> None:
    original = engine.answer_question

    async def slow(question: str, house, clauses, contract_id):
        if only is None or only in question:
            await asyncio.sleep(delay)
        return await original(question, house, clauses, contract_id)

    monkeypatch.setattr(engine, "answer_question", slow)


async def _messages(client, conversation_id: str) -> list[dict]:
    resp = await client.get(f"/api/v1/conversations/{conversation_id}/messages")
    assert resp.status_code == 200
    return resp.json()


async def test_concurrent_runs_keep_their_own_results_and_events(client, workspace, monkeypatch):
    _install_slow_answer(monkeypatch, delay=0.2)
    first = await create_conversation(client, workspace, "对话一")
    second = await create_conversation(client, workspace, "对话二")

    posted_a = await client.post(f"/api/v1/conversations/{first}/messages", json={"text": "物业费谁承担？"})
    posted_b = await client.post(f"/api/v1/conversations/{second}/messages", json={"text": "押金怎么退？"})
    run_a = await wait_run(client, posted_a.json()["run_id"])
    run_b = await wait_run(client, posted_b.json()["run_id"])
    assert run_a["status"] == "done" and run_b["status"] == "done"

    message_a = run_a["result"]["message_id"]
    message_b = run_b["result"]["message_id"]
    assert message_a != message_b
    assert [message["id"] for message in await _messages(client, first)] == [
        posted_a.json()["message_id"],
        message_a,
    ]
    assert [message["id"] for message in await _messages(client, second)] == [
        posted_b.json()["message_id"],
        message_b,
    ]

    events_a = await collect_events(client, posted_a.json()["run_id"])
    assert all(event["run_id"] == posted_a.json()["run_id"] for event in events_a)
    assert events_a[-1]["data"]["result"]["message_id"] == message_a


async def test_cancelling_one_run_does_not_affect_the_other(client, workspace, monkeypatch):
    _install_slow_answer(monkeypatch, delay=1.0)
    first = await create_conversation(client, workspace, "对话一")
    second = await create_conversation(client, workspace, "对话二")

    posted_a = await client.post(f"/api/v1/conversations/{first}/messages", json={"text": "物业费谁承担？"})
    posted_b = await client.post(f"/api/v1/conversations/{second}/messages", json={"text": "押金怎么退？"})
    run_a_id = posted_a.json()["run_id"]
    run_b_id = posted_b.json()["run_id"]
    await asyncio.sleep(0.05)

    cancelled = await client.post(f"/api/v1/runs/{run_a_id}/cancel")
    assert cancelled.json()["status"] == "cancelled"
    assert (await wait_run(client, run_a_id))["status"] == "cancelled"
    run_b = await wait_run(client, run_b_id)
    assert run_b["status"] == "done"

    assert len(await _messages(client, first)) == 1  # 被取消的运行不写回答
    messages_b = await _messages(client, second)
    assert messages_b[-1]["id"] == run_b["result"]["message_id"]


async def test_finished_old_run_does_not_write_into_new_conversation(client, workspace, monkeypatch):
    _install_slow_answer(monkeypatch, delay=0.4, only="慢")
    slow_conversation = await create_conversation(client, workspace, "慢对话")
    new_conversation = await create_conversation(client, workspace, "新对话")

    posted_slow = await client.post(
        f"/api/v1/conversations/{slow_conversation}/messages", json={"text": "慢问题：物业费谁承担？"}
    )
    posted_new = await client.post(
        f"/api/v1/conversations/{new_conversation}/messages", json={"text": "押金怎么退？"}
    )
    run_new = await wait_run(client, posted_new.json()["run_id"])
    run_slow = await wait_run(client, posted_slow.json()["run_id"])
    assert run_slow["status"] == "done" and run_new["status"] == "done"

    messages_new = await _messages(client, new_conversation)
    assert len(messages_new) == 2  # 旧 run 完成后没有再往新会话追加消息
    assert run_slow["result"]["message_id"] not in {message["id"] for message in messages_new}
    messages_slow = await _messages(client, slow_conversation)
    assert messages_slow[-1]["id"] == run_slow["result"]["message_id"]
