import unittest

from contact_utils import emails_from_text, is_company_social_url, normalize_company, phones_from_text, unwrap_redirect


class UtilsTest(unittest.TestCase):
    def test_email(self):
        self.assertEqual(emails_from_text("Email sales@example.com"), ["sales@example.com"])

    def test_phone_filters_followers(self):
        self.assertEqual(phones_from_text("28,849,947 followers Call +91 98765 43210"), ["+91 98765 43210"])

    def test_company_social(self):
        self.assertTrue(is_company_social_url("https://www.linkedin.com/company/microsoft/"))
        self.assertFalse(is_company_social_url("https://www.linkedin.com/in/example/"))

    def test_redirect(self):
        self.assertEqual(unwrap_redirect("https://l.facebook.com/l.php?u=https%3A%2F%2Fexample.com"), "https://example.com")

    def test_company_normalization(self):
        self.assertEqual(normalize_company("Example Pvt. Ltd."), "example")


if __name__ == "__main__":
    unittest.main()

