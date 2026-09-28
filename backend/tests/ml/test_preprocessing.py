"""Preprocesamiento compartido: se ajusta con train, se aplica igual en serve."""
from __future__ import annotations

import math

import pytest

from agrosense.ml.preprocessing import PreprocessorParams, fit_preprocessor, transform

ROWS = [
    {"x": 1.0, "y": None, "c": "a"},
    {"x": None, "y": 2.0, "c": None},
    {"x": 3.0, "y": 5.0, "c": "b"},
    {"x": 10.0, "y": 1.0, "c": "a"},
]


def test_missing_numbers_take_the_training_median():
    params = fit_preprocessor(ROWS, ("x", "y"), ("c",))
    assert params.medians == {"x": 3.0, "y": 2.0}


def test_standardizes_with_population_std_of_the_imputed_column():
    params = fit_preprocessor(ROWS, ("x", "y"), ("c",))
    imputed = [1.0, 3.0, 3.0, 10.0]
    mean = sum(imputed) / 4
    std = math.sqrt(sum((v - mean) ** 2 for v in imputed) / 4)
    assert params.means["x"] == pytest.approx(mean)
    assert params.scales["x"] == pytest.approx(std)
    row = transform(params, [{"x": 10.0, "y": 2.0, "c": "a"}])[0]
    assert row[0] == pytest.approx((10.0 - mean) / std)


def test_missing_category_takes_the_mode_and_one_hot_follows_sorted_categories():
    params = fit_preprocessor(ROWS, ("x", "y"), ("c",))
    assert params.modes == {"c": "a"}
    assert params.feature_names == ["x", "y", "c=a", "c=b"]
    assert transform(params, [{"x": 1.0, "y": 1.0, "c": None}])[0][2:] == [1.0, 0.0]


def test_unknown_category_encodes_as_all_zeros():
    params = fit_preprocessor(ROWS, ("x", "y"), ("c",))
    assert transform(params, [{"x": 1.0, "y": 1.0, "c": "nueva"}])[0][2:] == [0.0, 0.0]


def test_constant_column_is_not_divided_by_zero():
    params = fit_preprocessor([{"x": 2.0}, {"x": 2.0}], ("x",), ())
    assert params.scales["x"] == 1.0
    assert transform(params, [{"x": 2.0}]) == [[0.0]]


def test_a_column_without_any_value_in_training_is_an_error():
    with pytest.raises(ValueError, match="x"):
        fit_preprocessor([{"x": None}, {"x": None}], ("x",), ())


def test_params_roundtrip_through_json():
    params = fit_preprocessor(ROWS, ("x", "y"), ("c",))
    assert PreprocessorParams.from_json(params.to_json()) == params


def test_fit_only_sees_the_rows_it_is_given():
    train = fit_preprocessor(ROWS[:2], ("x", "y"), ("c",))
    assert train.medians["x"] == 1.0  # el 10.0 de la fila 4 no se filtra al ajuste


def test_matches_sklearn_column_transformer():
    np = pytest.importorskip("numpy")
    pd = pytest.importorskip("pandas")
    pytest.importorskip("sklearn")
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    serve = ROWS + [{"x": 2.0, "y": 3.0, "c": "zzz"}]
    params = fit_preprocessor(ROWS, ("x", "y"), ("c",))
    ours = np.asarray(transform(params, serve))

    df = pd.DataFrame(serve)
    df[["x", "y"]] = df[["x", "y"]].astype(float)
    df["c"] = df["c"].map(lambda v: np.nan if v is None else v)
    ct = ColumnTransformer(
        [
            ("num", make_pipeline(SimpleImputer(strategy="median"), StandardScaler()), ["x", "y"]),
            (
                "cat",
                make_pipeline(
                    SimpleImputer(strategy="most_frequent"),
                    OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                ),
                ["c"],
            ),
        ]
    )
    ct.fit(df.iloc[: len(ROWS)])
    np.testing.assert_allclose(ours, ct.transform(df), atol=1e-12)
