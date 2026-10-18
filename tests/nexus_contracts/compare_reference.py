"""Optional offline TS/Python comparison against hash-pinned NXB-0 sources.

Run from repository root; see docs/architecture/nexus-python-contracts.md.
No downloads, product processes or Nexus domain operations are performed.
"""

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import random
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "agent"))
from jarvis_agent.nexus_contracts.canonical import canonical_json, parse_canonical_file
from jarvis_agent.nexus_contracts.validation import validate_contract

SOURCE_BLOBS = {
    "canonical.ts": "de324f3a9b6536354fdff24b6b2240d9287d905d",
    "schema.ts": "044016e15de42e89d0f3b9219252fbaf408fa93e",
    "contracts.ts": "1a862b44db3e4dab57ac1bfa692ab0cf678665cc",
}
CORPUS = ROOT / "tests" / "fixtures" / "local-integration-v1"


def objects(value, path=()):
    if isinstance(value, dict):
        yield path, value
        for key, item in value.items():
            yield from objects(item, path + (key,))
    elif isinstance(value, list):
        for key, item in enumerate(value):
            yield from objects(item, path + (key,))


def target(value, path):
    for key in path:
        value = value[key]
    return value


def mutations(cases):
    result = []
    for case in cases:
        if not case["valid"]:
            continue
        for path, value in objects(case["document"]):
            for key in list(value) + ["UNREVIEWED_FIELD"]:
                for replacement in [None, True, False, 0, 1, "", [], {}, "bad\n"]:
                    document = copy.deepcopy(case["document"])
                    target(document, path)[key] = replacement
                    result.append({"schema": case["schema"], "document": document})
                if key in value:
                    document = copy.deepcopy(case["document"])
                    del target(document, path)[key]
                    result.append({"schema": case["schema"], "document": document})
    return result


ORACLE = r"""
const fs=require("node:fs"), path=require("node:path"), crypto=require("node:crypto");
const {validateContract,JSON_SCHEMA_DOCUMENT}=require(process.argv[1]+"/contracts.js");
const {canonicalJson,canonicalBytes,parseCanonicalFile}=require(process.argv[1]+"/canonical.js");
const corpus=name=>parseCanonicalFile(fs.readFileSync(path.join(process.argv[2],name)));
const cases=corpus("conformance.json").cases, vectors=corpus("canonicalization.json").cases;
const schemaFailures=cases.filter(c=>validateContract(c.schema,c.document).valid!==c.valid).length;
const canonicalFailures=vectors.filter(c=>{
  const bytes=Buffer.from(canonicalBytes(JSON.parse(c.input)));
  return bytes.toString("utf8")!==c.canonical || bytes.toString("hex")!==c.utf8Hex
    || crypto.createHash("sha256").update(bytes).digest("hex")!==c.sha256;
}).length;
if(canonicalJson(JSON_SCHEMA_DOCUMENT)!==canonicalJson(corpus("wire-v1.schema.json"))) throw Error("Schema drift");
const input=JSON.parse(fs.readFileSync(0,"utf8"));
console.log(JSON.stringify({
  schemaCases:cases.length,schemaFailures,canonicalVectors:vectors.length,canonicalFailures,
  mutations:input.mutations.map(c=>validateContract(c.schema,c.document).valid),
  numbers:input.numbers.map(h=>canonicalJson(Buffer.from(h,"hex").readDoubleBE()))
}));
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-source", required=True, type=Path)
    parser.add_argument("--node", default="node")
    parser.add_argument("--compiler", type=Path, default=ROOT / "node_modules/typescript/bin/tsc")
    options = parser.parse_args()
    for name, expected in SOURCE_BLOBS.items():
        raw = (options.reference_source / name).read_bytes()
        blob = b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
        if hashlib.sha1(blob).hexdigest() != expected:
            raise ValueError(f"NXB-0 source blob mismatch: {name}")
    cases = parse_canonical_file((CORPUS / "conformance.json").read_bytes())["cases"]
    mutants = mutations(cases)
    rng = random.Random(454)
    numbers = []
    while len(numbers) < 10_000:
        raw = rng.getrandbits(64).to_bytes(8, "big")
        if math.isfinite(struct.unpack(">d", raw)[0]):
            numbers.append(raw.hex())
    with tempfile.TemporaryDirectory(prefix="yjnx-conformance-") as scratch:
        subprocess.run([
            options.node, str(options.compiler), "--strict", "--skipLibCheck",
            "--target", "es2022", "--module", "commonjs", "--outDir", scratch,
            str(options.reference_source.resolve() / "contracts.ts"),
        ], check=True, timeout=60)
        reference = subprocess.run(
            [options.node, "-e", ORACLE, scratch, str(CORPUS)],
            input=json.dumps({"mutations": mutants, "numbers": numbers}, ensure_ascii=True),
            capture_output=True, text=True, encoding="utf-8", check=True, timeout=180,
        )
        expected = json.loads(reference.stdout)
    schema_mismatches = sum(
        validate_contract(case["schema"], case["document"]).valid != valid
        for case, valid in zip(mutants, expected.pop("mutations"), strict=True)
    )
    number_mismatches = sum(
        canonical_json(struct.unpack(">d", bytes.fromhex(bits))[0]) != spelling
        for bits, spelling in zip(numbers, expected.pop("numbers"), strict=True)
    )
    report = dict(expected, schemaMutations=len(mutants), schemaMismatches=schema_mismatches,
                  binary64Samples=len(numbers), numberMismatches=number_mismatches)
    print(json.dumps(report, sort_keys=True))
    if any(report[key] for key in ("schemaFailures", "canonicalFailures", "schemaMismatches", "numberMismatches")):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
