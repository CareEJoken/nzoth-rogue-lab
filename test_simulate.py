import random
import unittest

from simulate import *


def state(kinds, mana=3, **kwargs):
    hand = [Card(i + 10, kind, shadow=kind == SHADOW) for i, kind in enumerate(kinds)]
    return State([], hand, turn=3, mana=mana, **kwargs)


def play(s, kind, target=""):
    c = next(c for c in s.hand if c.kind == kind)
    apply(s, ("play", c.uid, target), random.Random(1))


def execute_win(s):
    for _ in range(20):
        plan = tactical(*tac_args(s))
        if not plan:
            return False
        apply(s, actual_action(s, plan[0]), random.Random(1))
        if s.started:
            return True
    raise AssertionError("tactical loop")


class OpeningRandom(random.Random):
    """Force an opening hand while keeping replacement draws reproducible."""

    def __init__(self, kinds):
        super().__init__(1)
        self.kinds = kinds
        self.first_shuffle = True

    def shuffle(self, deck):
        if not self.first_shuffle:
            return super().shuffle(deck)
        self.first_shuffle = False
        selected = []
        for kind in self.kinds:
            selected.append(deck.pop(next(i for i, c in enumerate(deck) if c.kind == kind)))
        deck[:0] = selected


class EngineTests(unittest.TestCase):
    def test_deck_code(self):
        heroes, cards = decode_deck(DECK_CODE)
        self.assertEqual(heroes, [930])
        self.assertEqual(cards, dict(zip(DBF, COPIES)))
        self.assertEqual(sum(cards.values()), 30)

    def test_costs_match_downloaded_card_snapshot(self):
        cards = json.loads((ROOT / "cards_enUS.json").read_text(encoding="utf-8"))
        for c in cards:
            k = DBF.index(c["dbfId"])
            self.assertEqual(COST[k], c["cost"])
            self.assertEqual(k in MINIONS, c["type"] == "MINION")
            self.assertEqual(k in SPELLS, c["type"] == "SPELL")

    def test_uncomboed_swindle_only_spell(self):
        s = state([SWINDLE], mana=2)
        s.deck = [Card(1, ICE), Card(2, STEP)]
        play(s, SWINDLE)
        self.assertEqual([c.kind for c in s.hand], [STEP])
        self.assertEqual([c.kind for c in s.deck], [ICE])

    def test_comboed_swindle_spell_then_minion(self):
        s = state([COIN, SWINDLE], mana=1)
        s.deck = [Card(1, ICE), Card(2, STEP)]
        play(s, COIN)
        play(s, SWINDLE)
        self.assertEqual([c.kind for c in s.hand], [STEP, ICE])

    def test_shroud_without_replacement(self):
        s = state([PREP, SHROUD], mana=1)
        s.deck = [Card(1, ICE), Card(2, NZOTH), Card(3, COIN)]
        play(s, PREP)
        play(s, SHROUD)
        self.assertEqual({c.kind for c in s.hand}, {ICE, NZOTH})
        self.assertEqual(s.mana, 0)

    def test_dig_last_minion_guaranteed(self):
        s = state([DIG], mana=1)
        s.deck = [Card(1, STEP), Card(2, NZOTH), Card(3, COIN)]
        play(s, DIG)
        self.assertEqual([c.kind for c in s.hand], [NZOTH])

    def test_t3_replay_ice(self):
        s = state([ICE, STEP, KOBOLD, NZOTH], mana=3)
        play(s, ICE)
        play(s, STEP, "ice")
        play(s, ICE)
        self.assertEqual(s.ice_discount, 2)
        self.assertEqual(s.mana, 2)
        self.assertIsNone(tactical(*tac_args(s)))
        s.mana = 3
        play(s, KOBOLD)
        self.assertTrue(s.started)

    def test_t4_baseline(self):
        s = state([KOBOLD, NZOTH], mana=4, ice_discount=1)
        self.assertTrue(execute_win(s))
        self.assertEqual(s.mana, 0)
        self.assertEqual(s.deathrattle_summons, 1)
        self.assertEqual(card_cost(s, s.hand[0]), 14)

    def test_cards_ready_without_mana_not_success(self):
        s = state([KOBOLD, NZOTH], mana=3, ice_discount=1)
        self.assertIsNone(tactical(*tac_args(s)))

    def test_coin_t3(self):
        s = state([COIN, KOBOLD, NZOTH], mana=3, ice_discount=1)
        self.assertTrue(execute_win(s))

    def test_hand_ice_contaminates_kobold(self):
        s = state([ICE, KOBOLD, NZOTH], mana=4, ice_discount=1, board_ice=True)
        self.assertIsNone(tactical(*tac_args(s)))
        play(s, KOBOLD)
        self.assertFalse(s.started)

    def test_bone_requires_target(self):
        s = state([PREP, BONE, KOBOLD, NZOTH], mana=2, ice_discount=1)
        self.assertIsNone(tactical(*tac_args(s)))
        s.board_ice = True
        self.assertTrue(execute_win(s))

    def test_bone_next_card(self):
        s = state([BONE, KOBOLD, NZOTH], mana=4, ice_discount=1, board_ice=True)
        play(s, BONE, "ice")
        self.assertEqual(s.next_discount, 2)
        self.assertEqual(s.mana, 2)
        play(s, KOBOLD)
        self.assertTrue(s.started)

    def test_bone_kills_unarmed_kobold(self):
        s = state([PREP, BONE, NZOTH], mana=0, board_kobold=True)
        self.assertTrue(execute_win(s))

    def test_trade_preserves_order_no_combo(self):
        s = state([BLADE], mana=1, prep=2, next_discount=2)
        s.deck = [Card(1, NZOTH), Card(2, ICE), Card(3, KOBOLD)]
        apply(s, ("trade", s.hand[0].uid, ""), random.Random(2))
        self.assertEqual([c.kind for c in s.hand], [NZOTH])
        self.assertFalse(s.combo)
        self.assertEqual((s.prep, s.next_discount), (2, 2))
        self.assertEqual([c.kind for c in s.deck if c.kind != BLADE], [ICE, KOBOLD])

    def test_dredge_without_combo_waits(self):
        s = state([FISH], mana=1)
        s.deck = [Card(1, EVASION), Card(2, STEP), Card(3, NZOTH), Card(4, COIN)]
        play(s, FISH)
        self.assertEqual(s.hand, [])
        self.assertEqual(s.deck[0].kind, NZOTH)

    def test_dredge_combo_draws_chosen(self):
        s = state([FISH], mana=1, combo=True)
        s.deck = [Card(1, EVASION), Card(2, STEP), Card(3, NZOTH), Card(4, COIN)]
        play(s, FISH)
        self.assertEqual([c.kind for c in s.hand], [NZOTH])

    def test_map_not_automatic_two_draws(self):
        s = state([MAP], mana=2)
        s.deck = [Card(1, NZOTH), Card(2, COIN), Card(3, EVASION)]
        play(s, MAP)
        self.assertEqual(len(s.hand), 1)
        self.assertEqual(len(s.deck), 2)
        self.assertEqual(s.hand[0].kind, NZOTH)

    def test_map_second_choice_requires_play(self):
        s = state([MAP], mana=3, ice_discount=1)
        s.deck = [Card(1, COIN), Card(2, STEP), Card(3, EVASION)]
        play(s, MAP)
        self.assertEqual(s.hand[0].kind, COIN)
        play(s, COIN)
        self.assertEqual(len(s.hand), 1)
        self.assertEqual(len(s.deck), 1)

    def test_map_second_choice_expires(self):
        s = state([MAP], mana=2)
        s.deck = [Card(1, COIN), Card(2, STEP), Card(3, EVASION)]
        play(s, MAP)
        s.turn += 1
        play(s, s.hand[0].kind)
        self.assertEqual(len(s.hand), 0)
        self.assertEqual(len(s.deck), 2)

    def test_discover_options_distinct(self):
        s = state([])
        s.deck = [Card(i, COIN) for i in range(6)] + [Card(8, ICE), Card(9, NZOTH)]
        self.assertEqual(set(discover_options(s, random.Random(1))), {COIN, ICE, NZOTH})

    def test_pick_draws_on_attack(self):
        s = state([PICK], mana=2)
        s.deck = [Card(1, NZOTH), Card(2, COIN)]
        play(s, PICK)
        self.assertEqual(len(s.hand), 0)
        apply(s, ("attack", -1, ""), random.Random(1))
        self.assertEqual(len(s.hand), 1)
        self.assertEqual(s.durability, 1)
        with self.assertRaises(AssertionError):
            apply(s, ("attack", -1, ""), random.Random(1))

    def test_shadow_permanent_discount_not_prep(self):
        s = state([PREP, SHROUD, SHADOW], mana=2)
        s.hand[1] = replace(s.hand[1], delta=-1)
        play(s, PREP)
        play(s, SHROUD)
        shadow = next(c for c in s.hand if c.shadow)
        self.assertEqual(shadow.kind, SHROUD)
        self.assertEqual(card_cost(s, shadow), 2)

    def test_shadow_coin_chain(self):
        s = state([COIN, SHADOW, KOBOLD, NZOTH], mana=2, ice_discount=1)
        self.assertTrue(execute_win(s))

    def test_tactical_policy_has_no_deck_order_input(self):
        s = state([ICE, PREP, SHROUD, STEP], mana=2)
        s.deck = [Card(1, NZOTH), Card(2, COIN), Card(3, KOBOLD), Card(4, MAP)]
        a = choose_action(s, random.Random(1))
        s.deck.reverse()
        self.assertEqual(a, choose_action(s, random.Random(1)))

    def test_policy_planning_does_not_consume_rng(self):
        rng = random.Random(4)
        s = state([ICE, PREP, SHROUD, STEP], mana=2)
        s.deck = [Card(1, NZOTH), Card(2, COIN), Card(3, KOBOLD)]
        before = rng.getstate()
        choose_action(s, rng)
        self.assertEqual(before, rng.getstate())

    def test_hand_limit(self):
        s = state([COIN] * 10)
        s.deck = [Card(1, NZOTH)]
        draw(s, random.Random(1))
        self.assertEqual(len(s.hand), 10)
        self.assertEqual(s.burned, 1)

    def test_mulligan_conservation(self):
        for second in (False, True):
            s, _, _ = mulligan(random.Random(1), second, "guide")
            self.assertEqual(len(s.hand), 5 if second else 3)
            self.assertEqual(len(s.hand) + len(s.deck), 31 if second else 30)
            self.assertEqual(len({c.uid for c in s.hand + s.deck}), 31 if second else 30)

    def test_mulligan_rejected_entities_not_in_replacements(self):
        for seed in range(1000):
            s, _, rejected = mulligan(random.Random(seed), seed % 2 == 0, "guide")
            self.assertFalse({c.uid for c in rejected} & {c.uid for c in s.hand})

    def test_combo_keeps_prep_swindle_pair(self):
        s, opening, rejected = mulligan(OpeningRandom([PREP, SWINDLE, STEP]), False, "combo")
        self.assertEqual([c.kind for c in rejected], [STEP])
        self.assertTrue({c.uid for c in opening[:2]} <= {c.uid for c in s.hand})

    def test_combo_keeps_prep_shroud_pair(self):
        s, opening, rejected = mulligan(OpeningRandom([PREP, SHROUD, EVASION]), False, "combo")
        self.assertEqual([c.kind for c in rejected], [EVASION])
        self.assertTrue({c.uid for c in opening[:2]} <= {c.uid for c in s.hand})

    def test_combo_keeps_duplicate_prep_and_draw_cards(self):
        for kinds in ([PREP, PREP, SWINDLE, SHROUD], [PREP, SWINDLE, SWINDLE, SHROUD]):
            s, opening, rejected = mulligan(OpeningRandom(kinds), True, "combo")
            self.assertEqual(rejected, [])
            self.assertEqual(s.hand[:-1], opening)

    def test_combo_does_not_keep_lone_prep_or_other_draw_pair(self):
        for kinds in ([PREP, STEP, EVASION], [PREP, DIG, STEP], [PREP, MAP, STEP]):
            _, _, rejected = mulligan(OpeningRandom(kinds), False, "combo")
            self.assertIn(PREP, [c.kind for c in rejected])

    def test_combo_still_keeps_baseline_cards_without_prep(self):
        for kinds in ([ICE, KOBOLD, NZOTH], [DIG, SWINDLE, SHROUD]):
            _, _, rejected = mulligan(OpeningRandom(kinds), False, "combo")
            self.assertEqual(rejected, [])

    def test_guide_still_rejects_prep_in_pair(self):
        for draw_kind in (SWINDLE, SHROUD):
            _, _, rejected = mulligan(OpeningRandom([PREP, draw_kind, STEP]), False, "guide")
            self.assertEqual([c.kind for c in rejected], [PREP, STEP])

    def test_combo_condition_only_uses_original_opening(self):
        # Replacement cards cannot retroactively make a rejected Prep worth keeping.
        for second in (False, True):
            for seed in range(300):
                s, opening, rejected = mulligan(random.Random(seed), second, "combo")
                should_keep = any(c.kind in (SWINDLE, SHROUD) for c in opening)
                for c in opening:
                    if c.kind == PREP:
                        self.assertEqual(c not in rejected, should_keep)
                self.assertFalse({c.uid for c in rejected} & {c.uid for c in s.hand})

    def test_smoke_and_trace_replay(self):
        for seed in range(200):
            args = (seed % 2 == 0, seed % 3 == 0, "guide", False, 2)
            a = game(random.Random(seed), *args)
            b = game(random.Random(seed), *args, record=True)
            self.assertEqual((a[0], a[2]), (b[0], b[2]))


if __name__ == "__main__":
    unittest.main()
