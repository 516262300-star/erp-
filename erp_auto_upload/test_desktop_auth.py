import unittest
from unittest.mock import Mock, patch
from config import Settings
from erp.login import login
from erp_desktop_auth import DesktopLoginRequired

class MiniappDesktopTests(unittest.TestCase):
    def test_no_password_configuration_required(self):
        self.assertIn('/login/profile', Settings().require_login())

    def test_missing_client_does_not_touch_business_page(self):
        page = Mock()
        with patch('erp.login.get_client_cookies', side_effect=DesktopLoginRequired('login needed')):
            with self.assertRaises(DesktopLoginRequired):
                login(page, Settings().require_login())
        page.goto.assert_not_called()
        page.locator.assert_not_called()

    def test_client_cookie_login_never_fills_password(self):
        page = Mock()
        page.content.return_value = '<a onclick="logout()">退出</a>'
        page.url = Settings().require_login()
        cookies = [{'name': 'session', 'value': 'synthetic', 'domain': 'ldswj.net'}]
        with patch('erp.login.get_client_cookies', return_value=cookies):
            login(page, page.url)
        page.context.add_cookies.assert_called_once_with(cookies)
        page.locator.return_value.fill.assert_not_called()

if __name__ == '__main__':
    unittest.main()
