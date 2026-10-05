import os

from account_kit.config import AccountKitConfig
from account_kit.emailer import render_code_email, _safe_template_name


def _config(**kwargs) -> AccountKitConfig:
    kwargs.setdefault("jwt_secret", "test-secret")
    kwargs.setdefault("brand_name", "Acme")
    return AccountKitConfig(**kwargs)


def test_login_2fa_uses_dedicated_template():
    subject, body = render_code_email(_config(), "login_2fa", "123456", "zh")
    assert "登录验证码" in subject
    assert "Acme" in subject
    assert "123456" in body
    assert "密码可能已泄露" in body
    assert "Acme" in body


def test_disable_2fa_uses_dedicated_template_en():
    subject, body = render_code_email(_config(), "disable_2fa", "654321", "en")
    assert "two-step verification" in subject.lower() or "turn off" in subject.lower()
    assert "Acme" in subject
    assert "654321" in body
    assert "compromised" in body


def test_register_still_uses_verification_template():
    subject, body = render_code_email(_config(), "register", "111222", "zh")
    assert subject == "【Acme】验证码"
    assert "注册账户" in body
    assert "111222" in body


def test_host_template_dir_overrides_same_name(tmp_path):
    (tmp_path / "verification_zh.html").write_text("HOST {{ code }} {{ brand }}", encoding="utf-8")
    config = _config(email_template_dir=str(tmp_path))
    _, body = render_code_email(config, "register", "999111", "zh")
    assert body == "HOST 999111 Acme"


def test_host_template_dir_falls_back_to_package(tmp_path):
    config = _config(email_template_dir=str(tmp_path))
    _, body = render_code_email(config, "login_2fa", "888777", "zh")
    assert "888777" in body
    assert "密码可能已泄露" in body


def test_email_template_map(tmp_path):
    (tmp_path / "custom.html").write_text("CUSTOM {{ code }}", encoding="utf-8")
    config = _config(
        email_template_dir=str(tmp_path),
        email_template_map={"register": "custom.html"},
    )
    _, body = render_code_email(config, "register", "000111", "zh")
    assert body == "CUSTOM 000111"


def test_email_template_map_lang_placeholder(tmp_path):
    (tmp_path / "alt_en.html").write_text("ALT {{ code }}", encoding="utf-8")
    config = _config(
        email_template_dir=str(tmp_path),
        email_template_map={"reset_password": "alt_{lang}.html"},
    )
    _, body = render_code_email(config, "reset_password", "444555", "en")
    assert body == "ALT 444555"


def test_template_map_rejects_traversal():
    config = _config(email_template_map={"register": "../../etc/passwd"})
    _, body = render_code_email(config, "register", "123456", "zh")
    assert "123456" in body
    assert "注册账户" in body


def test_safe_template_name():
    assert _safe_template_name("two_factor_login_zh.html") == "two_factor_login_zh.html"
    assert _safe_template_name("nested/ok.html") == "nested/ok.html"
    assert _safe_template_name("../secret.html") is None
    assert _safe_template_name("/etc/passwd") is None
    assert _safe_template_name("foo/../../etc/passwd") is None
    assert _safe_template_name("..\\windows") is None
    assert os.path.isabs(_safe_template_name("ok.html") or "") is False
