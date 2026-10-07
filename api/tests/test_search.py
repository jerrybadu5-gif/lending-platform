from app.domain.search import match_score, rank

PEOPLE = [
    ("Mary Kila", "Department of Health", "70123344", "2009 1182 4410"),
    ("Peter Wambi", "Lae Port Services", "71234567", "2011 0488 7712"),
    ("Joyce Ilave", "Teaching Service", "72220011", None),
    ("Kila Morea", "Department of Education", "75551212", None),
]


def find(q):
    return rank(q, PEOPLE, lambda p: match_score(q, p[0], [p[1]], [p[2], p[3]]), lambda p: p[0], 10)


def names(q):
    return [p[0] for p in find(q)]


def test_any_case_any_order_and_part_words():
    assert names("MARY") == ["Mary Kila"]
    assert names("kila mary") == ["Mary Kila"]
    assert names("mar ki") == ["Mary Kila"]
    assert names("ilave") == ["Joyce Ilave"]


def test_small_typos():
    assert names("Joyse") == ["Joyce Ilave"]
    assert names("wambee") == []  # two letters out is too far
    assert names("Peetr") == ["Peter Wambi"]  # two letters swapped


def test_name_matches_rank_above_employer_matches():
    assert names("kila")[:2] == ["Kila Morea", "Mary Kila"]
    assert names("education") == ["Kila Morea"]


def test_numbers_match_on_digits():
    assert names("7012 3344") == ["Mary Kila"]
    assert names("+675 7123-4567") == []  # the 675 prefix isn't part of the stored number
    assert names("71234567") == ["Peter Wambi"]
    assert names("2011-0488-7712") == ["Peter Wambi"]
    assert names("0488") == ["Peter Wambi"]
    assert names("7012 3") == ["Mary Kila"]  # still typing


def test_empty_query_lists_everyone_by_name():
    assert names("") == ["Joyce Ilave", "Kila Morea", "Mary Kila", "Peter Wambi"]
