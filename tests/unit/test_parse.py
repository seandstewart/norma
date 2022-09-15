import inspect
from unittest import mock

import pytest
import sqlparse.tokens

from yesql.core import parse


def test_clean_comment():
    # Given
    comment = "-- Comments 4 U "
    expected = "Comments 4 U"
    # When
    cleaned = parse._clean_comment(comment)
    # Then
    assert cleaned == expected


def test_split_comments():
    # Given
    comments = """
    /** I've got a lot to say.

    And I'm gonna say it. **/
    """
    expected = ["I've got a lot to say.", "", "And I'm gonna say it."]
    # When
    split = parse._split_comments(comments)
    # Then
    assert split == expected


def test_normalize_parameters_asyncpg():
    # Given
    statement = "select * from foo where blar=$1, bar=:bar::bar"
    posarg = inspect.Parameter(
        "arg1",
        kind=inspect.Parameter.POSITIONAL_ONLY,
    )
    kwdarg = inspect.Parameter(
        "bar",
        kind=inspect.Parameter.KEYWORD_ONLY,
    )
    posargs = {"$1": posarg}
    kwdargs = {":bar": kwdarg}
    expected_sql = "select * from foo where blar=$1, bar=$2::bar"
    expected_remapping = {kwdarg.name: 2}
    # When
    sql, remapping = parse._normalize_parameters(
        statement=statement,
        driver="asyncpg",
        posargs=posargs,
        kwdargs=kwdargs,
    )
    # Then
    assert (sql, remapping) == (expected_sql, expected_remapping)


def test_normalize_parameters_psycopg():
    # Given
    statement = "select * from foo where blar=:blar, bar=:bar::bar"
    kwdargs = {
        ":bar": inspect.Parameter(
            "bar",
            kind=inspect.Parameter.KEYWORD_ONLY,
        ),
        ":blar": inspect.Parameter(
            "blar",
            kind=inspect.Parameter.KEYWORD_ONLY,
        ),
    }

    expected_sql = "select * from foo where blar=%(blar)s, bar=%(bar)s::bar"
    expected_remapping = None
    # When
    sql, remapping = parse._normalize_parameters(
        statement=statement,
        driver="psycopg",
        posargs={},
        kwdargs=kwdargs,
    )
    # Then
    assert (sql, remapping) == (expected_sql, expected_remapping)


def test_normalize_parameters_no_kwdargs():
    # Given
    statement = "select * from foo where blar=$1, bar=$2"
    # When
    sql, remapping = parse._normalize_parameters(
        statement=statement, driver="asyncpg", posargs={}, kwdargs={}
    )
    # Then
    assert (sql, None) == (statement, None)


def test_gather_parameters():
    # Given
    token = _mock_token()
    ttype = sqlparse.tokens.Name.Placeholder
    filtered = _mock_token()
    params = {}
    expected_posargs = {}
    expected_kwdargs = {}
    for pname, pout, posarg in [
        ("$foo", "foo", False),
        ("%(bar)s", "bar", False),
        ("%()s", "arg1", True),
        (":2", "arg2", True),
    ]:

        params[pout] = (_mock_token(ttype=ttype, value=pname), posarg)
        if posarg:
            expected_posargs[pname] = inspect.Parameter(
                name=pout,
                kind=inspect.Parameter.POSITIONAL_ONLY,
            )
        else:
            expected_kwdargs[pname] = inspect.Parameter(
                name=pout, kind=inspect.Parameter.KEYWORD_ONLY
            )
    token.flatten.return_value = [filtered, *(t for t, p in params.values())]
    # When
    posargs, kwdargs = parse._gather_parameters(token)
    # Then
    assert (posargs, kwdargs) == (expected_posargs, expected_kwdargs)


def test_process_sql():
    # Given
    given_sql = "select * from foo where blar=$1, bar=:bar::bar"
    ttype = sqlparse.tokens.Name.Placeholder
    given_sub_tokens = [
        _mock_token(ttype=ttype, value="$1"),
        _mock_token(ttype=ttype, value=":bar"),
    ]
    given_token = _mock_token(
        __str__=lambda _: given_sql,
        tokens=[_mock_token(flatten=lambda: given_sub_tokens)],
    )
    expected_sig = inspect.Signature(
        [
            inspect.Parameter("arg1", kind=inspect.Parameter.POSITIONAL_ONLY),
            inspect.Parameter("bar", kind=inspect.Parameter.KEYWORD_ONLY),
        ]
    )
    expected_sql = "select * from foo where blar=$1, bar=$2::bar"
    expected_remapping = {"bar": 2}
    # When
    sql, sig, remapping = parse.process_sql(
        statement=given_token,
        start=0,
        driver="asyncpg",
    )
    # Then
    assert (sql, sig, remapping) == (expected_sql, expected_sig, expected_remapping)


@pytest.mark.parametrize(
    argnames="lead,expected_name,expected_modifier",
    argvalues=[
        ("foo", None, parse.MANY),
        (":name foo", "foo", parse.MANY),
        (":name foo :many", "foo", parse.MANY),
        (":name foo :one", "foo", parse.ONE),
        (":name foo :scalar", "foo", parse.SCALAR),
        (":name foo :multi", "foo", parse.MULTI),
        (":name foo :affected", "foo", parse.AFFECTED),
        (":name foo :raw", "foo", parse.RAW),
        (":name foo :*", "foo", parse.MANY),
        (":name foo :^", "foo", parse.ONE),
        (":name foo :$", "foo", parse.SCALAR),
        (":name foo :!", "foo", parse.MULTI),
        (":name foo :#", "foo", parse.AFFECTED),
        (":name foo :~", "foo", parse.RAW),
    ],
)
def test_get_funcop(lead, expected_name, expected_modifier):
    # When
    name, modifier = parse.get_funcop(lead=lead)
    # Then
    assert (name, modifier) == (expected_name, expected_modifier)


def _mock_token(**overrides):
    m = mock.Mock(**overrides)
    return m