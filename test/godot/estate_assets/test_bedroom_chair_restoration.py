"""All 32 formal bedroom chairs retain approved V003 petal geometry."""

from collections import Counter

from test.godot.asset_geometry import _Model
from test.godot.estate_assets.test_bed_shape_restoration import ROOT, _geometry

# Frozen accessor digests from approved V003 at HEAD 52db08c5.
EXPECTED = {
    "Chair | central tall back petal": [
        (
            (
                (
                    "NORMAL",
                    "8f775c5789710de432f2807f736a378d3a546ecdf87d85a6f075078057baf2e4",
                ),
                (
                    "POSITION",
                    "e48e4838d3584491aac07554499055a4026024df3179a8be1b3ab75f12201278",
                ),
                (
                    "TEXCOORD_0",
                    "bad4db8fb0acf43375028a67558381504875b851df4a581f7f35f25b211a5e26",
                ),
            ),
            "f8f7d30f29889aa06c022a08c7c7c8cbcc47fdf19ea5495c892180dcfe81f49e",
        )
    ],
    "Chair | central tall back petal tailored inner seam": [
        (
            (
                (
                    "NORMAL",
                    "3b8ebb510674f18309e2f65d8654755c9a65c22f6906513db43d79cc7216af3c",
                ),
                (
                    "POSITION",
                    "709b78798b65ed3bd49a363729f254df07443a2595ccadcfe8fb36dd3e81b8a1",
                ),
            ),
            "7a82ea78a8a0dd96adce5876ad6abd62b8dffcd9a121ddfab814325be8be9ac4",
        )
    ],
    "Chair | left back petal": [
        (
            (
                (
                    "NORMAL",
                    "4263a983cbeef6dbc2f0839f5ec1fdb3e88f12b31aaaec9b888880d2e458f12c",
                ),
                (
                    "POSITION",
                    "b1096612f3529dfc94c817bea23b4dca761afdb26d09ea99af84d0893f481913",
                ),
                (
                    "TEXCOORD_0",
                    "fdf7715b8af94557dbf2a8f0515bf0e4267dafdbbc91b1ff2fd36002e7be04c5",
                ),
            ),
            "30d6dfed5e912139732bb3d0160eba05bb992f8bbc6e3502b5d57891eb35b119",
        )
    ],
    "Chair | left back petal tailored inner seam": [
        (
            (
                (
                    "NORMAL",
                    "d470a1ff590d23ba920777b9c75539ca21b6b728350852529e71d00f44f80df1",
                ),
                (
                    "POSITION",
                    "37ad74b9108f18a6663d749e90a4453b502195c57e3db6a894ca6a95aee1f955",
                ),
            ),
            "69b791c7a1e693c11712992442e2a3060719fd4ed2edcfb8cedd57d2a6e3852e",
        )
    ],
    "Chair | left cupped arm petal": [
        (
            (
                (
                    "NORMAL",
                    "25352aab82e4b344b291b7d852e69a536e8837ef23eaea6b1b0f136642b50fc5",
                ),
                (
                    "POSITION",
                    "6ec71263e2f35c3f29e5a93869fbafcf95466896799843a55a187a08b99ad9f5",
                ),
                (
                    "TEXCOORD_0",
                    "5432d46c283e79d5861d708db258a664dbf633bae1bc50819898e6321f8a8896",
                ),
            ),
            "e026393217243b0b94f174c145a27fdcb062ba7ec2b28654298c11a03eae9338",
        )
    ],
    "Chair | left cupped arm petal tailored inner seam": [
        (
            (
                (
                    "NORMAL",
                    "a889c0e1c9d628c2abec8e5759cf8b97a8df70da91b47a439d6bb9c133943c80",
                ),
                (
                    "POSITION",
                    "604cd081051f59ad0c04b61f0eb6f779e0900da69537bbd1093ccc9c861aa634",
                ),
            ),
            "f28133cdf0b30d57f4eca6f0b188cd6a974a061c8f725652007257fa871b3b1a",
        )
    ],
    "Chair | right back petal": [
        (
            (
                (
                    "NORMAL",
                    "f6ddedcf7c96004f12a781ecd447798aac3bf88ceeaf11883d2e53bbc82e2e17",
                ),
                (
                    "POSITION",
                    "1d352c942aeff09340b7a7950fa0edd693caeaa005e7f0f70ea974ed6c440e84",
                ),
                (
                    "TEXCOORD_0",
                    "57dac420c1293f63033c6fa9474450114dfdc5fd634bba03ac52a51138163507",
                ),
            ),
            "3930c527c577f6afcfb3754454d4f606357b5f93d94e8ca270b8f4af3e6a5bd6",
        )
    ],
    "Chair | right back petal tailored inner seam": [
        (
            (
                (
                    "NORMAL",
                    "5140a4fd79a9ab1fdedd9f0c559f0a93b9a32f895fe78f715ef62d12b812d1e3",
                ),
                (
                    "POSITION",
                    "fa9daaaee1978cea375fc6d1cdc03d7b2a13117146a7f2c4100ce6a6e0aa166c",
                ),
            ),
            "6b0d11a5eebc132bdbde8512d7c4515eeed1e1e73cb9287e0e3a5215e7db76e0",
        )
    ],
    "Chair | right cupped arm petal": [
        (
            (
                (
                    "NORMAL",
                    "550995793fa31e9722c75db0c407c72c9e2fb6d05172ea734d4efaf4c5de20ec",
                ),
                (
                    "POSITION",
                    "9105bf7f2e363da9198d04933fbcf45f9619991064ca239269640a549717f59b",
                ),
                (
                    "TEXCOORD_0",
                    "9f1cf1462d6abc3cfecd58acb8dfb44571f6c33dfa6f433e4b1d5ed46c11dea0",
                ),
            ),
            "51694cc56ff43024b2e05449eeb7e610054e599cd581d41b6187e4468255b497",
        )
    ],
    "Chair | right cupped arm petal tailored inner seam": [
        (
            (
                (
                    "NORMAL",
                    "25977768500cfaf76637921e6b52400997358017cba356a20af95e382763a65f",
                ),
                (
                    "POSITION",
                    "33a80cb00ba98ce7f0ce54f68cbec029f2506048c08c194ee73cb5762841dd80",
                ),
            ),
            "d3f0e1c105e5501c72f489c46d76d2644f1148c6d1210047179e18e66a33cf79",
        )
    ],
}


def test_chair_petals_and_seams_match_original():
    actual = _Model(
        str(ROOT / "godot_project/nest/estate/ElfieNest-complete-final.glb")
    )
    seen = Counter()
    for node in actual.doc["nodes"]:
        name = node.get("extras", {}).get("source_name")
        if "mesh" not in node or name not in EXPECTED:
            continue
        assert _geometry(actual, node["mesh"]) == EXPECTED[name], node["name"]
        seen[name] += 1
    assert seen == Counter(dict.fromkeys(EXPECTED, 32))
