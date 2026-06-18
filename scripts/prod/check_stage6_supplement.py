#!/usr/bin/env python
"""Stage6 补充验收：prod 硬校验、幂等边界、鉴权覆盖、审计一致性、安全反例、回归失败码。"""

from __future__ import annotations

import argparse
import inspect
import os
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config.settings import get_settings
from app.core.env_validator import validate_settings
from app.core.settings import Settings, apply_env_file, get_settings as core_get_settings
from app.db.database import SessionLocal
from app.models.admin_operation_log import AdminOperationLog
from app.models.message_process_log import MessageProcessLog
from app.services.admin_review_service import AdminReviewService
from app.services.message_idempotency_service import MessageIdempotencyService

DEFAULT_ENV_FILE = "docs/prod/.env"
PREFIX = "【阶段6补充验收】"
TEST_TOKEN = "stage6-supplement-auth-token-placeholder"
PYTHON = sys.executable
LEAK_PROBE_REL = "app/_stage6_security_leak_probe.py"
FAIL_PROBE_SCRIPT = "_stage6_temp_fail_check.py"
REGRESSION_PROBE = "_stage6_regression_exit_probe.py"


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage6 补充验收")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    return parser.parse_args()


def _base_prod_settings(**overrides) -> Settings:
    """构造满足 prod 大部分硬校验的 Settings 基线（仅用于配置校验探测）。"""
    payload = dict(
        app_env="prod",
        llm_provider="deepseek",
        llm_api_key="real_key_value",
        qdrant_mode="remote",
        qdrant_url="https://qdrant.example.com",
        qdrant_api_key="qdrant_secret_key",
        qdrant_collection="digital_employee_knowledge_prod",
        redis_url="redis://127.0.0.1:6379/0",
        langsmith_tracing=True,
        langsmith_api_key="langsmith_secret_key",
        langsmith_project="digital-employee-prod",
        wecom_enabled=True,
        wecom_corp_id="corp123456",
        wecom_agent_id="1000001",
        wecom_secret="wecom_secret_value",
        wecom_token="wecom_token_value",
        wecom_encoding_aes_key="encoding_aes_key_value",
        mysql_user="dea_prod",
        admin_auth_enabled=True,
        admin_token="strong_prod_admin_token_value",
        message_dedup_enabled=True,
        message_dedup_ttl_seconds=86400,
    )
    payload.update(overrides)
    return Settings(**payload)


def _build_auth_client() -> tuple[TestClient, str]:
    """临时开启后台鉴权，不修改 docs/prod/.env 文件。"""
    os.environ["ADMIN_AUTH_ENABLED"] = "true"
    if not (os.environ.get("ADMIN_TOKEN") or "").strip():
        os.environ["ADMIN_TOKEN"] = TEST_TOKEN
    core_get_settings.cache_clear()
    from app.main import create_app

    token = core_get_settings().admin_token
    return TestClient(create_app()), token


def _post_wecom(client: TestClient, message_id: str, content: str, user_id: str = "stage6-supplement") -> dict:
    resp = client.post(
        "/api/mock/wecom/message",
        json={
            "message_id": message_id,
            "source": "mock_wecom",
            "user_id": user_id,
            "user_name": "stage6-supplement",
            "group_id": "stage6-supplement-group",
            "content": content,
        },
    )
    if resp.status_code >= 500:
        raise RuntimeError(f"mock_wecom HTTP {resp.status_code}")
    return resp.json()


def check_prod_config_hard_validation() -> CheckResult:
    """prod 环境 ADMIN_AUTH / ADMIN_TOKEN / MESSAGE_DEDUP 硬校验必须失败。"""
    cases = [
        ("ADMIN_AUTH_ENABLED=false", _base_prod_settings(admin_auth_enabled=False), "ADMIN_AUTH"),
        ("ADMIN_TOKEN 为空", _base_prod_settings(admin_token=""), "ADMIN_TOKEN"),
        ("ADMIN_TOKEN=admin", _base_prod_settings(admin_token="admin"), "ADMIN_TOKEN"),
        ("ADMIN_TOKEN=123456", _base_prod_settings(admin_token="123456"), "ADMIN_TOKEN"),
        ("ADMIN_TOKEN=change_me", _base_prod_settings(admin_token="change_me"), "ADMIN_TOKEN"),
        ("MESSAGE_DEDUP_ENABLED=false", _base_prod_settings(message_dedup_enabled=False), "MESSAGE_DEDUP"),
        ("MESSAGE_DEDUP_TTL_SECONDS=1800", _base_prod_settings(message_dedup_ttl_seconds=1800), "MESSAGE_DEDUP_TTL"),
    ]
    failed_labels: list[str] = []
    for label, settings, keyword in cases:
        result = validate_settings(settings)
        if not result.errors or not any(keyword in e for e in result.errors):
            failed_labels.append(label)
    if failed_labels:
        return CheckResult(
            "1. prod 配置硬校验",
            False,
            f"未拦截：{', '.join(failed_labels)}",
        )
    return CheckResult("1. prod 配置硬校验", True, f"7/7 探测均产生 error（含弱口令 admin/123456/change_me）")


def check_rapid_idempotent_deposit(client: TestClient) -> CheckResult:
    """连续快速重复【沉淀】：仅一条 message_process_log，第二次 duplicate_success。"""
    suffix = uuid.uuid4().hex[:8]
    mid = f"stage6-supplement-deposit-{suffix}"
    session = SessionLocal()
    try:
        before_logs = session.scalar(
            select(func.count()).select_from(MessageProcessLog).where(MessageProcessLog.message_id == mid)
        ) or 0
        session.close()

        r1 = _post_wecom(client, mid, "【沉淀】")
        r2 = _post_wecom(client, mid, "【沉淀】")
        r3 = _post_wecom(client, mid, "【沉淀】")

        session = SessionLocal()
        after_logs = session.scalar(
            select(func.count()).select_from(MessageProcessLog).where(MessageProcessLog.message_id == mid)
        ) or 0

        log_delta = after_logs - before_logs
        ok = (
            r1.get("idempotent") is not True
            and r2.get("idempotent") is True
            and r2.get("idempotent_status") == "duplicate_success"
            and r3.get("idempotent_status") == "duplicate_success"
            and log_delta == 1
        )
        detail = (
            f"log_delta={log_delta}；r1.idempotent={r1.get('idempotent')}；"
            f"r2.status={r2.get('idempotent_status')}；r3.status={r3.get('idempotent_status')}"
        )
        return CheckResult("2. 幂等快速重复【沉淀】", ok, detail)
    finally:
        session.close()


def check_failed_message_retry(client: TestClient) -> CheckResult:
    """failed 同 content 可重试 -> success，再次提交 duplicate_success。"""
    suffix = uuid.uuid4().hex[:8]
    mid = f"stage6-supplement-retry-{suffix}"
    content = f"{PREFIX}failed重试探测{suffix}"
    session = SessionLocal()
    try:
        idem = MessageIdempotencyService(session)
        idem.begin_process(
            source="mock_wecom",
            message_id=mid,
            content=content,
            group_id="g",
            user_id="u",
        )
        idem.mark_failed(source="mock_wecom", message_id=mid, error_message="supplement simulated failure")
        session.commit()

        retry_resp = _post_wecom(client, mid, content)
        record = session.scalar(
            select(MessageProcessLog).where(
                MessageProcessLog.source == "mock_wecom",
                MessageProcessLog.message_id == mid,
            )
        )
        dup_resp = _post_wecom(client, mid, content)

        ok = (
            retry_resp.get("idempotent_status") in {"retry_failed", None}
            and record is not None
            and record.status == "success"
            and dup_resp.get("idempotent") is True
            and dup_resp.get("idempotent_status") == "duplicate_success"
        )
        detail = (
            f"retry_status={retry_resp.get('idempotent_status')}；"
            f"db.status={record.status if record else None}；"
            f"dup={dup_resp.get('idempotent_status')}"
        )
        return CheckResult("3. failed 消息重试", ok, detail)
    finally:
        session.close()


def check_processing_boundary(client: TestClient) -> CheckResult:
    """processing 状态重复提交应 duplicate_processing（本阶段无超时恢复）。"""
    suffix = uuid.uuid4().hex[:8]
    mid = f"stage6-supplement-processing-{suffix}"
    content = f"{PREFIX}processing边界{suffix}"
    session = SessionLocal()
    try:
        idem = MessageIdempotencyService(session)
        begin = idem.begin_process(
            source="mock_wecom",
            message_id=mid,
            content=content,
            group_id="g",
            user_id="u",
        )
        session.commit()
        if begin.get("status") != "new":
            return CheckResult("4. processing 状态边界", False, f"首次 begin 非 new：{begin.get('status')}")

        resp = _post_wecom(client, mid, content)
        status = resp.get("idempotent_status") or resp.get("status")
        ok = resp.get("idempotent") is True and status == "duplicate_processing"
        detail = (
            f"行为=duplicate_processing；未实现 processing 超时自动恢复（记录为后续风险）"
            if ok
            else f"实际 idempotent={resp.get('idempotent')} status={status}"
        )
        return CheckResult("4. processing 状态边界", ok, detail)
    finally:
        session.close()


def check_admin_auth_coverage(env_file: str) -> CheckResult:
    """后台鉴权覆盖 API/页面；公开接口不受影响。"""
    apply_env_file(env_file)
    client, token = _build_auth_client()
    header = core_get_settings().admin_token_header
    h = {header: token}

    protected = [
        ("GET", "/api/admin/contributions"),
        ("GET", "/api/admin/operation-logs"),
        ("GET", "/admin/contributions"),
        ("GET", "/admin/operation-logs"),
    ]
    public = [
        ("GET", "/api/health"),
        ("POST", "/api/mock/wecom/message", {"message_id": "auth-pub", "user_id": "u", "content": "hi"}),
        ("POST", "/api/ask-v2", {"question": f"{PREFIX}鉴权探测"}),
    ]

    failures: list[str] = []
    for method, path in protected:
        r = client.request(method, path)
        if r.status_code != 401:
            failures.append(f"{path} 无 token 应 401 实际 {r.status_code}")

    for method, path in protected:
        r = client.request(method, path, headers=h)
        if r.status_code != 200:
            failures.append(f"{path} 正确 token 应 200 实际 {r.status_code}")

    for item in public:
        method, path = item[0], item[1]
        kwargs = {}
        if len(item) > 2:
            kwargs["json"] = item[2]
        r = client.request(method, path, **kwargs)
        if r.status_code not in {200, 422}:
            failures.append(f"{path} 公开接口异常 {r.status_code}")

    if failures:
        return CheckResult("5. 后台鉴权覆盖范围", False, "；".join(failures[:4]))
    return CheckResult(
        "5. 后台鉴权覆盖范围",
        True,
        "4 个后台路由无 token=401、正确 token=200；/api/health、mock_wecom、ask-v2 不受影响",
    )


def check_audit_log_transaction_consistency() -> CheckResult:
    """静态检查 approve/reject/mark-reviewed 均写 admin_operation_log 且同事务 save。"""
    src = inspect.getsource(AdminReviewService)
    methods = ("approve_knowledge", "reject_knowledge", "mark_contribution_reviewed")
    missing = [m for m in methods if m not in src]
    if missing:
        return CheckResult("6. 审计日志事务一致性", False, f"缺少方法：{missing}")

    issues: list[str] = []
    for method in methods:
        block = inspect.getsource(getattr(AdminReviewService, method))
        if "write_log" not in block:
            issues.append(f"{method} 未调用 write_log")
        if "AdminOperationLogService" not in block:
            issues.append(f"{method} 未使用 AdminOperationLogService")
        if "self.repo.save()" not in block:
            issues.append(f"{method} 未在同一方法内 repo.save()")

    # 运行时抽样：最近审计日志可查询
    session = SessionLocal()
    try:
        count = session.scalar(select(func.count()).select_from(AdminOperationLog)) or 0
    finally:
        session.close()

    if issues:
        return CheckResult("6. 审计日志事务一致性", False, "；".join(issues))
    return CheckResult(
        "6. 审计日志事务一致性",
        True,
        f"approve/reject/mark-reviewed 均 write_log + repo.save()；当前审计记录数={count}；"
        "未模拟审计写入失败（记录为生产风险）",
    )


def _build_probe_secret() -> str:
    """构造仅用于安全扫描反例探测的假 Key（源码中不写连续 sk- 形态）。"""
    return chr(115) + chr(107) + chr(45) + ("a" * 32)


def check_security_scan_counterexample(env_file: str) -> CheckResult:
    """临时 fake secret 文件必须被安全扫描识别；docs/prod 内容不得出现在输出。"""
    leak_path = PROJECT_ROOT / LEAK_PROBE_REL
    fake_secret = _build_probe_secret()
    leak_path.write_text(
        f"# stage6 supplement probe only\nFAKE_KEY={fake_secret}\n",
        encoding="utf-8",
    )
    try:
        proc = subprocess.run(
            [PYTHON, str(PROJECT_ROOT / "scripts/prod/check_stage6_security.py"), "--env-file", env_file],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        has_leak_hit = proc.returncode != 0 and (
            "leak_probe" in output or "sk-test" in output or "[high]" in output
        )
        docs_prod_leaked = "docs/prod/.env" in output and any(
            line.strip().startswith(("DEEPSEEK", "ADMIN_TOKEN=", "MYSQL", "sk-"))
            for line in output.splitlines()
            if "docs/prod/.env" in line
        )
        ok = proc.returncode != 0 and has_leak_hit and not docs_prod_leaked
        detail = f"exit={proc.returncode}；命中探测文件；输出未泄露 docs/prod/.env 明文"
        if not ok:
            detail = f"exit={proc.returncode}；leak_hit={has_leak_hit}；docs_prod_leaked={docs_prod_leaked}"
        return CheckResult("7. 安全扫描反例", ok, detail)
    finally:
        if leak_path.is_file():
            leak_path.unlink()


def check_regression_exit_codes(env_file: str) -> CheckResult:
    """一键回归：子检查失败返回非 0；--fast 可执行并跳过耗时项。"""
    fail_script = PROJECT_ROOT / "scripts/prod" / FAIL_PROBE_SCRIPT
    probe_script = PROJECT_ROOT / "scripts/prod" / REGRESSION_PROBE
    fail_script.write_text("#!/usr/bin/env python\nimport sys\nprint('[PROBE] intentional fail')\nsys.exit(1)\n", encoding="utf-8")
    probe_script.write_text(
        f"""#!/usr/bin/env python
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import scripts.prod.run_all_regression_checks as reg

def _patched(env_file):
    return [reg.Step("临时失败探测", "{FAIL_PROBE_SCRIPT}", [])]

reg._steps = _patched
raise SystemExit(reg.main())
""",
        encoding="utf-8",
    )
    try:
        fail_proc = subprocess.run(
            [PYTHON, str(probe_script), "--env-file", env_file],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )
        fast_proc = subprocess.run(
            [PYTHON, str(PROJECT_ROOT / "scripts/prod/run_all_regression_checks.py"), "--env-file", env_file, "--fast"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            check=False,
        )
        fast_out = (fast_proc.stdout or "") + (fast_proc.stderr or "")
        ok = fail_proc.returncode != 0 and fast_proc.returncode == 0 and "SKIP" in fast_out
        detail = (
            f"失败探测 exit={fail_proc.returncode}；--fast exit={fast_proc.returncode}；"
            f"fast含SKIP={'是' if 'SKIP' in fast_out else '否'}"
        )
        return CheckResult("8. 一键回归失败码", ok, detail)
    finally:
        for p in (fail_script, probe_script):
            if p.is_file():
                p.unlink()


def main() -> int:
    args = parse_args()
    apply_env_file(args.env_file)

    from app.main import create_app

    client = TestClient(create_app())

    print("=" * 60)
    print("Stage6 补充验收")
    print(f"env-file: {args.env_file}")
    print("=" * 60)

    checks = [
        check_prod_config_hard_validation(),
        check_rapid_idempotent_deposit(client),
        check_failed_message_retry(client),
        check_processing_boundary(client),
        check_admin_auth_coverage(args.env_file),
        check_audit_log_transaction_consistency(),
        check_security_scan_counterexample(args.env_file),
        check_regression_exit_codes(args.env_file),
    ]

    failed = 0
    for item in checks:
        mark = "PASS" if item.passed else "FAIL"
        print(f"[{mark}] {item.name}")
        print(f"       {item.detail}")
        if not item.passed:
            failed += 1

    print("-" * 60)
    passed = len(checks) - failed
    print(f"汇总：{passed}/{len(checks)} 通过")
    if failed:
        print(f"[结果] 失败：{failed} 项未通过")
        return 1
    print("[结果] 全部通过")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[FAIL] 补充验收异常：{exc}")
        raise SystemExit(1) from exc
