"""The refund-claim list is a heuristic. These phrases are the ones it knows."""

from agent_runtime.refund_claims import stated_refund_cents, text_claims_refund_done


def test_known_english_claims() -> None:
    claims = (
        "Your refund was processed.",
        "Your refund of 0 cents was processed.",
        "The refund has been issued.",
        "We've sent your money back.",
        "We have sent your money back.",
        "Your money was sent back.",
        "Refund processed.",
        "We already sent your money back.",
        "The amount was credited.",
        "It was credited to your account.",
        "We have returned the charge.",
    )
    for text in claims:
        assert text_claims_refund_done(text), text


def test_negation_and_unrelated_text_are_not_claims() -> None:
    quiet = (
        "No refund was issued.",
        "The refund was not processed.",
        "The amount was not credited.",
        "We never sent your money back.",
        "A reviewer rejected the refund. No money moved.",
        "The order id is not valid.",
    )
    for text in quiet:
        assert not text_claims_refund_done(text), text


def test_zero_cents_is_a_stated_amount() -> None:
    assert stated_refund_cents("Refund of 0 cents was processed.") == 0
    assert stated_refund_cents("Refund of zero cents was processed.") == 0
    assert stated_refund_cents("Refund of 4200 cents was processed.") == 4200
