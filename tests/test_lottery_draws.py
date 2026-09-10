import unittest
from datetime import date
from unittest.mock import AsyncMock, patch

from lottery_draws import _parse_wclc_results, fetch_draw_results


def draw_html(numbers=(12, 18, 19, 35, 43, 49, 52), bonus=26):
    balls = "".join(f'<li class="pastWinNumber">{n}</li>' for n in numbers)
    if bonus is not None:
        balls += f'<li class="pastWinNumberBonus"><span class="pastWinNumberBonusText">Bonus</span>{bonus}</li>'
    return f'<div class="pastWinNumDate">Tuesday, September 08, 2026</div><ul class="pastWinNumbers">{balls}</ul>'


class ResultParsingTests(unittest.TestCase):
    def test_published_max_draw(self):
        self.assertEqual(_parse_wclc_results(draw_html(), date(2026, 9, 8), 7, 52), {
            "numbers": [12, 18, 19, 35, 43, 49, 52], "bonus": 26, "draw_date": "2026-09-08",
        })

    def test_missing_date(self):
        self.assertIsNone(_parse_wclc_results(draw_html(), date(2026, 9, 4), 7, 52))

    def test_invalid_or_incomplete_draw_never_borrows_other_balls(self):
        extra = '<ul class="pastWinNumbers"><li class="pastWinNumber">7</li></ul>'
        for numbers, bonus in [((12, 18, 19, 35, 43, 49), 26),
                               ((12, 12, 19, 35, 43, 49, 52), 26),
                               ((12, 18, 19, 35, 43, 49, 53), 26),
                               ((12, 18, 19, 35, 43, 49, 52), None),
                               ((12, 18, 19, 35, 43, 49, 52), 12)]:
            with self.subTest(numbers=numbers, bonus=bonus):
                self.assertIsNone(_parse_wclc_results(draw_html(numbers, bonus) + extra, date(2026, 9, 8), 7, 52))

    def test_game_information_is_not_a_result(self):
        self.assertIsNone(_parse_wclc_results('September 08, 2026' + ''.join(f'<b>{n}</b>' for n in range(1, 10)), date(2026, 9, 8), 7, 52))


class ResultLookupTests(unittest.IsolatedAsyncioTestCase):
    async def test_direct_source_precedes_actor(self):
        with patch('lottery_draws._fetch_html', AsyncMock(return_value=draw_html())) as fetch, patch('lottery_draws.fetch_draw_results_apify', AsyncMock()) as actor:
            result = await fetch_draw_results('lotto_max', '2026-09-08')
            self.assertEqual(result['bonus'], 26)
            self.assertIn('/winning-numbers/', fetch.call_args.args[0])
            actor.assert_not_awaited()

    async def test_actor_fallback(self):
        expected = {'numbers': [12, 18, 19, 35, 43, 49, 52], 'bonus': 26}
        with patch('lottery_draws._fetch_html', AsyncMock(return_value=None)), patch('lottery_draws.fetch_draw_results_apify', AsyncMock(return_value=expected)) as actor:
            self.assertEqual(await fetch_draw_results('lotto_max', '2026-09-08'), expected)
            actor.assert_awaited_once_with('lotto_max', '2026-09-08', 7, 52)

    async def test_invalid_input(self):
        for value in (None, '', 'invalid'):
            self.assertIsNone(await fetch_draw_results('lotto_max', value))


if __name__ == '__main__':
    unittest.main()
