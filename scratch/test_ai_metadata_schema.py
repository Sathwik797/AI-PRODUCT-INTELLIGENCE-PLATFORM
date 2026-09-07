import sys
sys.path.insert(0, ".")

import json
from pydantic import ValidationError

from app.schemas.ai_metadata import (
    AIProductMetadata,
    ArrayField,
    ArrayNode,
    BooleanField,
    BooleanNode,
    CategoryField,
    CategoryRecommendationValue,
    DimensionsField,
    DimensionsNode,
    DimensionsValue,
    Evidence,
    ImageEvidenceSource,
    InferredEvidenceSource,
    MeasurementField,
    MeasurementNode,
    NumberField,
    NumberNode,
    ObjectField,
    ObjectNode,
    RangeField,
    RangeNode,
    RangeValue,
    SellerEvidenceSource,
    TextField,
    TextNode,
)

print("=" * 60)
print("RUNNING AI PRODUCT METADATA SCHEMA VALIDATION SUITE")
print("=" * 60)

passed = 0
failed = 0

def run_test(name, fn):
    global passed, failed
    try:
        fn()
        print(f"[PASS] {name}")
        passed += 1
    except Exception as e:
        print(f"[FAIL] {name} -> {e}")
        failed += 1

# A. Valid text field
def test_a():
    f = TextField.model_validate({
        "type": "text",
        "value": "Breathable Mesh Fabric",
        "confidence": 0.95,
        "evidence": {
            "source": {"type": "image", "image_id": 10},
            "explanation": "Texture is clearly visible on the upper."
        }
    })
    assert f.value == "Breathable Mesh Fabric"
    assert f.confidence == 0.95
    assert isinstance(f.evidence.source, ImageEvidenceSource)
    assert f.evidence.source.image_id == 10

run_test("A. Valid text field", test_a)

# B. Valid number field
def test_b():
    f = NumberField.model_validate({
        "type": "number",
        "value": 42.5,
        "confidence": 0.90,
        "evidence": {
            "source": {"type": "seller"},
            "explanation": "European shoe size stated in spec sheet."
        }
    })
    assert f.value == 42.5
    assert isinstance(f.evidence.source, SellerEvidenceSource)

run_test("B. Valid number field", test_b)

# C. Valid boolean field
def test_c():
    f = BooleanField.model_validate({
        "type": "boolean",
        "value": True,
        "confidence": 0.98,
        "evidence": {
            "source": {"type": "image", "image_id": 12},
            "explanation": "Waterproof Gore-Tex badge is clearly visible."
        }
    })
    assert f.value is True

run_test("C. Valid boolean field", test_c)

# D. Valid measurement
def test_d():
    f = MeasurementField.model_validate({
        "type": "measurement",
        "value": 1.5,
        "unit": "kg",
        "confidence": 0.85,
        "evidence": {
            "source": {"type": "seller"},
            "explanation": "Weight specification provided by seller."
        }
    })
    assert f.value == 1.5
    assert f.unit == "kg"

run_test("D. Valid measurement", test_d)

# E. Valid range
def test_e():
    f = RangeField.model_validate({
        "type": "range",
        "value": {"min": 0, "max": 40},
        "unit": "°C",
        "confidence": 0.88,
        "evidence": {
            "source": {"type": "inferred"},
            "explanation": "Standard operating temperature for consumer electronics."
        }
    })
    assert f.value.min == 0
    assert f.value.max == 40
    assert f.unit == "°C"

run_test("E. Valid range", test_e)

# F. Valid dimensions
def test_f():
    f = DimensionsField.model_validate({
        "type": "dimensions",
        "value": {"length": 20, "width": 10, "height": 5},
        "unit": "cm",
        "confidence": 0.82,
        "evidence": {
            "source": {"type": "image", "image_id": 4},
            "explanation": "Estimated against standard packaging scale."
        }
    })
    assert f.value.length == 20
    assert f.value.width == 10
    assert f.value.height == 5
    assert f.unit == "cm"

run_test("F. Valid dimensions", test_f)

# G. Valid typed array/object
def test_g():
    arr = ArrayField.model_validate({
        "type": "array",
        "value": [
            {"type": "text", "value": "Crimson Red"},
            {"type": "text", "value": "Obsidian Black"}
        ],
        "confidence": 0.95,
        "evidence": {
            "source": {"type": "image", "image_id": 1},
            "explanation": "Dual tone colorway observed across product body."
        }
    })
    assert len(arr.value) == 2
    assert arr.value[0].value == "Crimson Red"

    obj = ObjectField.model_validate({
        "type": "object",
        "value": {
            "upper": {"type": "text", "value": "Mesh"},
            "outsole": {"type": "text", "value": "Vibram Rubber"}
        },
        "confidence": 0.90,
        "evidence": {
            "source": {"type": "image", "image_id": 2},
            "explanation": "Material callout labels visible on product tag."
        }
    })
    assert "upper" in obj.value
    assert obj.value["upper"].value == "Mesh"

run_test("G. Valid typed array and object", test_g)

# H. Unknown value with value=null and valid evidence
def test_h():
    f = TextField.model_validate({
        "type": "text",
        "value": None,
        "confidence": 0.0,
        "evidence": {
            "source": {"type": "image", "image_id": 12},
            "explanation": "The material cannot be reliably determined from the provided image."
        }
    })
    assert f.value is None
    assert f.confidence == 0.0
    assert f.evidence is not None

run_test("H. Unknown value with value=null and valid evidence", test_h)

# I. Invalid confidence > 1
def test_i():
    try:
        TextField.model_validate({
            "type": "text",
            "value": "Test",
            "confidence": 1.05,
            "evidence": {
                "source": {"type": "seller"},
                "explanation": "Test explanation."
            }
        })
        raise AssertionError("Should have raised ValidationError for confidence > 1")
    except ValidationError:
        pass

run_test("I. Invalid confidence > 1 raises ValidationError", test_i)

# J. Invalid confidence < 0
def test_j():
    try:
        TextField.model_validate({
            "type": "text",
            "value": "Test",
            "confidence": -0.1,
            "evidence": {
                "source": {"type": "seller"},
                "explanation": "Test explanation."
            }
        })
        raise AssertionError("Should have raised ValidationError for confidence < 0")
    except ValidationError:
        pass

run_test("J. Invalid confidence < 0 raises ValidationError", test_j)

# K. Invalid/missing evidence
def test_k():
    try:
        TextField.model_validate({
            "type": "text",
            "value": "Test",
            "confidence": 0.8
            # missing evidence
        })
        raise AssertionError("Should have raised ValidationError for missing evidence")
    except ValidationError:
        pass

run_test("K. Invalid/missing evidence raises ValidationError", test_k)

# L. Invalid image evidence without image_id
def test_l():
    try:
        Evidence.model_validate({
            "source": {"type": "image"},
            "explanation": "Missing required image_id."
        })
        raise AssertionError("Should have raised ValidationError for missing image_id")
    except ValidationError:
        pass

run_test("L. Invalid image evidence without image_id raises ValidationError", test_l)

# M. Recursive structure exceeding depth 2
def test_m():
    # Depth 1: Array of Text -> valid
    # Depth 2: Array of Array of Text -> valid
    # Depth 3: Array of Array of Array of Text -> INVALID (> 2)
    depth_3_payload = {
        "type": "array",
        "value": [
            {
                "type": "array",
                "value": [
                    {
                        "type": "array",
                        "value": [
                            {"type": "text", "value": "Too deep"}
                        ]
                    }
                ]
            }
        ],
        "confidence": 0.5,
        "evidence": {
            "source": {"type": "seller"},
            "explanation": "Deeply nested list."
        }
    }
    try:
        ArrayField.model_validate(depth_3_payload)
        raise AssertionError("Should have raised ValidationError for recursive depth > 2")
    except ValidationError as e:
        assert "exceeds maximum allowed depth of 2" in str(e)

run_test("M. Recursive structure exceeding depth 2 raises ValidationError", test_m)

# N. Valid complete AIProductMetadata response
def test_n():
    complete_payload = {
        "title": {
            "type": "text",
            "value": "Nike Pegasus 40 Men's Road Running Shoes",
            "confidence": 0.96,
            "evidence": {
                "source": {"type": "image", "image_id": 1},
                "explanation": "Pegasus 40 branding visible on tongue and side profile."
            }
        },
        "description": {
            "type": "text",
            "value": "Springy ride for every run, familiar feel specifically engineered for neutral runners.",
            "confidence": 0.90,
            "evidence": {
                "source": {"type": "seller"},
                "explanation": "Product copy provided in seller catalog spec."
            }
        },
        "brand": {
            "type": "text",
            "value": "Nike",
            "confidence": 0.99,
            "evidence": {
                "source": {"type": "image", "image_id": 1},
                "explanation": "Swoosh logo prominently embossed on lateral side."
            }
        },
        "category": {
            "value": {
                "recommended_category_id": 1,
                "recommended_category_name": "Footwear",
                "proposed_category": "Men's Road Running Shoes"
            },
            "confidence": 0.94,
            "evidence": {
                "source": {"type": "image", "image_id": 1},
                "explanation": "Identified as athletic road footwear from tread and cushioning."
            }
        },
        "tags": ["running", "road-running", "cushioned", "athletic"],
        "keywords": ["nike pegasus", "men running shoes", "breathable sneaker", "daily trainer"],
        "attributes": {
            "weight": {
                "type": "measurement",
                "value": 288,
                "unit": "g",
                "confidence": 0.85,
                "evidence": {
                    "source": {"type": "seller"},
                    "explanation": "Official product technical specification sheet."
                }
            },
            "heel_to_toe_drop": {
                "type": "measurement",
                "value": 10,
                "unit": "mm",
                "confidence": 0.80,
                "evidence": {
                    "source": {"type": "seller"},
                    "explanation": "Geometry specs from technical documentation."
                }
            },
            "cushioning_range": {
                "type": "range",
                "value": {"min": 18, "max": 28},
                "unit": "mm",
                "confidence": 0.75,
                "evidence": {
                    "source": {"type": "inferred"},
                    "explanation": "Stack height range inferred from shoe silhouette."
                }
            },
            "box_dimensions": {
                "type": "dimensions",
                "value": {"length": 34.5, "width": 23.0, "height": 12.5},
                "unit": "cm",
                "confidence": 0.70,
                "evidence": {
                    "source": {"type": "inferred"},
                    "explanation": "Standard Nike men's shoebox dimensions."
                }
            },
            "waterproof": {
                "type": "boolean",
                "value": False,
                "confidence": 0.92,
                "evidence": {
                    "source": {"type": "image", "image_id": 2},
                    "explanation": "Single-layer engineered mesh upper is highly porous."
                }
            },
            "materials": {
                "type": "array",
                "value": [
                    {"type": "text", "value": "Engineered Mesh"},
                    {"type": "text", "value": "React Foam"},
                    {"type": "text", "value": "Waffle Rubber"}
                ],
                "confidence": 0.91,
                "evidence": {
                    "source": {"type": "image", "image_id": 3},
                    "explanation": "Close-up shots of upper, midsole, and outsole."
                }
            },
            "battery_capacity": {
                "type": "measurement",
                "value": None,
                "unit": None,
                "confidence": 0.0,
                "evidence": {
                    "source": {"type": "image", "image_id": 1},
                    "explanation": "Not applicable for traditional non-electronic footwear."
                }
            }
        }
    }
    metadata = AIProductMetadata.model_validate(complete_payload)
    assert metadata.title.value == "Nike Pegasus 40 Men's Road Running Shoes"
    assert metadata.category.value.recommended_category_id == 1
    assert len(metadata.tags) == 4
    assert len(metadata.attributes) == 7
    # Round-trip serialization check
    dumped = metadata.model_dump()
    assert dumped["attributes"]["weight"]["value"] == 288

run_test("N. Valid complete AIProductMetadata response", test_n)

# O. Invalid semantic type/value combination
def test_o():
    # 1. Measurement with non-numeric string
    try:
        MeasurementField.model_validate({
            "type": "measurement",
            "value": "one point five",
            "unit": "kg",
            "confidence": 0.8,
            "evidence": {"source": {"type": "seller"}, "explanation": "test"}
        })
        raise AssertionError("Should have rejected string value for measurement")
    except ValidationError:
        pass

    # 2. Measurement with value but missing unit
    try:
        MeasurementField.model_validate({
            "type": "measurement",
            "value": 1.5,
            "unit": None,
            "confidence": 0.8,
            "evidence": {"source": {"type": "seller"}, "explanation": "test"}
        })
        raise AssertionError("Should have rejected measurement without unit")
    except ValidationError:
        pass

    # 3. Boolean with string value 'true'
    try:
        BooleanField.model_validate({
            "type": "boolean",
            "value": "true",
            "confidence": 0.8,
            "evidence": {"source": {"type": "seller"}, "explanation": "test"}
        })
        raise AssertionError("Should have rejected string 'true' for strict boolean")
    except ValidationError:
        pass

    # 4. Range with min > max
    try:
        RangeField.model_validate({
            "type": "range",
            "value": {"min": 50, "max": 10},
            "unit": "°C",
            "confidence": 0.8,
            "evidence": {"source": {"type": "seller"}, "explanation": "test"}
        })
        raise AssertionError("Should have rejected range where min > max")
    except ValidationError:
        pass

run_test("O. Invalid semantic type/value combinations rejected", test_o)

# P. Explicit refinement check: Nested TypedNodes do NOT require confidence/evidence
def test_p():
    # Verify all nested TypedNodes instantiate with only typed values/structure (no confidence/evidence)
    t = TextNode.model_validate({"type": "text", "value": "red"})
    assert not hasattr(t, "confidence")
    assert not hasattr(t, "evidence")
    assert t.value == "red"

    n = NumberNode.model_validate({"type": "number", "value": 100})
    assert not hasattr(n, "confidence")
    assert not hasattr(n, "evidence")
    assert n.value == 100

    b = BooleanNode.model_validate({"type": "boolean", "value": False})
    assert not hasattr(b, "confidence")
    assert not hasattr(b, "evidence")
    assert b.value is False

    m = MeasurementNode.model_validate({"type": "measurement", "value": 50, "unit": "ml"})
    assert not hasattr(m, "confidence")
    assert not hasattr(m, "evidence")
    assert m.value == 50
    assert m.unit == "ml"

    r = RangeNode.model_validate({"type": "range", "value": {"min": 1, "max": 10}, "unit": "bar"})
    assert not hasattr(r, "confidence")
    assert not hasattr(r, "evidence")
    assert r.value.min == 1

    d = DimensionsNode.model_validate({"type": "dimensions", "value": {"length": 1, "width": 2, "height": 3}, "unit": "m"})
    assert not hasattr(d, "confidence")
    assert not hasattr(d, "evidence")
    assert d.value.height == 3

    arr = ArrayNode.model_validate({"type": "array", "value": [{"type": "text", "value": "val"}]})
    assert not hasattr(arr, "confidence")
    assert not hasattr(arr, "evidence")
    assert arr.value[0].value == "val"

    obj = ObjectNode.model_validate({"type": "object", "value": {"k": {"type": "number", "value": 1}}})
    assert not hasattr(obj, "confidence")
    assert not hasattr(obj, "evidence")
    assert obj.value["k"].value == 1

run_test("P. Nested TypedNodes do not have or require confidence/evidence", test_p)

# Q. Explicit refinement check: Top-level Field models MUST require confidence and evidence
def test_q():
    field_classes = [
        (TextField, {"type": "text", "value": "test"}),
        (NumberField, {"type": "number", "value": 123}),
        (BooleanField, {"type": "boolean", "value": True}),
        (MeasurementField, {"type": "measurement", "value": 10, "unit": "cm"}),
        (RangeField, {"type": "range", "value": {"min": 1, "max": 5}, "unit": "m"}),
        (DimensionsField, {"type": "dimensions", "value": {"length": 1, "width": 2, "height": 3}, "unit": "cm"}),
        (ArrayField, {"type": "array", "value": [{"type": "text", "value": "item"}]}),
        (ObjectField, {"type": "object", "value": {"key": {"type": "text", "value": "item"}}}),
    ]

    for cls, payload in field_classes:
        # Missing both confidence and evidence
        try:
            cls.model_validate(payload)
            raise AssertionError(f"{cls.__name__} should have rejected missing confidence and evidence")
        except ValidationError:
            pass

        # Missing evidence only
        payload_with_conf = {**payload, "confidence": 0.9}
        try:
            cls.model_validate(payload_with_conf)
            raise AssertionError(f"{cls.__name__} should have rejected missing evidence")
        except ValidationError:
            pass

        # Missing confidence only
        payload_with_ev = {
            **payload,
            "evidence": {
                "source": {"type": "seller"},
                "explanation": "Valid explanation."
            }
        }
        try:
            cls.model_validate(payload_with_ev)
            raise AssertionError(f"{cls.__name__} should have rejected missing confidence")
        except ValidationError:
            pass

        # Complete valid field
        payload_complete = {
            **payload,
            "confidence": 0.9,
            "evidence": {
                "source": {"type": "seller"},
                "explanation": "Valid explanation."
            }
        }
        instance = cls.model_validate(payload_complete)
        assert instance.confidence == 0.9
        assert instance.evidence.explanation == "Valid explanation."

run_test("Q. Top-level fields strictly require confidence and evidence", test_q)

# R. Explicit refinement check: Nested depth 2 works, depth 3 rejected
def test_r():
    # Depth 1: Array of Text
    a1 = ArrayField.model_validate({
        "type": "array",
        "value": [{"type": "text", "value": "a"}],
        "confidence": 0.9,
        "evidence": {"source": {"type": "seller"}, "explanation": "depth 1"}
    })
    assert len(a1.value) == 1

    # Depth 2: Array of Array of Text
    a2 = ArrayField.model_validate({
        "type": "array",
        "value": [
            {
                "type": "array",
                "value": [{"type": "text", "value": "nested"}]
            }
        ],
        "confidence": 0.9,
        "evidence": {"source": {"type": "seller"}, "explanation": "depth 2"}
    })
    assert len(a2.value) == 1
    assert a2.value[0].value[0].value == "nested"

    # Depth 3: Array of Array of Array of Text (REJECTED)
    try:
        ArrayField.model_validate({
            "type": "array",
            "value": [
                {
                    "type": "array",
                    "value": [
                        {
                            "type": "array",
                            "value": [{"type": "text", "value": "too deep"}]
                        }
                    ]
                }
            ],
            "confidence": 0.9,
            "evidence": {"source": {"type": "seller"}, "explanation": "depth 3"}
        })
        raise AssertionError("Should have rejected depth 3")
    except ValidationError:
        pass

run_test("R. Maximum depth 2 supported, depth 3 rejected", test_r)

print("=" * 60)
print(f"FINAL RESULTS: {passed} PASSED, {failed} FAILED")
print("=" * 60)
if failed > 0:
    sys.exit(1)
