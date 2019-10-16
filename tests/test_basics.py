import unittest
from flask import current_app
from app import create_app, db

from dotenv import load_dotenv
from pathlib import Path  # python3 only
env_path = Path('..') / '.env'
load_dotenv(dotenv_path=env_path)

class BasicsTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_app_exists(self):
        self.assertFalse(current_app is None)

    def test_app_is_testing(self):
        self.assertTrue(current_app.config['TESTING'])

    def test_homepage(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_template(self):
        response = self.client.get("/templates/")
        self.assertEqual(response.status_code, 200)

    # def test_run(self):
    #     response = self.client.get("/run/(notebook)")
    #     self.assertEqual(response.status_code, 200)


if __name__ == '__main__':

    unittest.main(BasicsTestCase().test_this())
