from __future__ import annotations

import json
import shutil

import pytest

from app.core.library import Library, LibraryError, normalize_keywords, safe_filename, slugify


def test_new_library_is_seeded(lib):
    assert lib.created
    mods = lib.modules()
    assert len(mods) >= 5
    py = lib.module("python-fundamentals")
    assert py is not None and py.name == "Python Fundamentals"
    assert py.topic("control-flow").name == "Control Flow"
    assert (lib.root / ".gitignore").read_text(encoding="utf-8").startswith(".index/")
    assert lib.module_name(None) == "Unsorted"
    assert lib.topic_name("python-fundamentals", "functions") == "Functions"


def test_add_resource_copies_file_and_signals(lib, make_file):
    events, commits = [], []
    lib.changed.connect(events.append)
    lib.commit_requested.connect(lambda msg, paths: commits.append((msg, paths)))
    src = make_file("loops.txt", "for and while loops")
    r = lib.add_resource(src, "", "python-fundamentals", "control-flow", "notes", " Intro ",
                         ["Loops", "#loops", "  iteration "], uploader="Ana")
    assert r.title == "loops"
    assert r.description == "Intro"
    assert r.keywords == ["Loops", "iteration"]
    assert r.path == "resources/python-fundamentals/loops.txt"
    assert lib.file_path(r).read_text(encoding="utf-8") == "for and while loops"
    assert r.size == len("for and while loops") and len(r.sha256) == 64
    assert events == ["resources"]
    msg, paths = commits[0]
    assert "loops" in msg and r.path in paths and "data/resources.json" in paths
    assert lib.counts()["python-fundamentals"] == 1 and lib.counts()["__all__"] == 1
    assert lib.resource(r.id) == r


def test_add_resource_validation(lib, make_file, tmp_path):
    src = make_file("a.txt")
    with pytest.raises(LibraryError):
        lib.add_resource(tmp_path / "missing.txt", "x", "python-fundamentals")
    with pytest.raises(LibraryError):
        lib.add_resource(src, "x", "no-such-module")
    with pytest.raises(LibraryError):
        lib.add_resource(src, "x", "python-fundamentals", kind="bogus")
    r = lib.add_resource(src, "x", "python-fundamentals", topic_id="not-a-topic")
    assert r.topic_id is None


def test_duplicate_file_names_get_unique_paths(lib, make_file):
    src = make_file("same.txt")
    a = lib.add_resource(src, "A", "python-fundamentals")
    b = lib.add_resource(src, "B", "python-fundamentals")
    assert a.path != b.path
    assert b.path.endswith("same 2.txt")


def test_update_and_move_resource(lib, make_file):
    r = lib.add_resource(make_file("oop.txt", "classes"), "OOP", "python-fundamentals", "functions")
    old_path = lib.file_path(r)
    u = lib.update_resource(r.id, title="Classes", keywords=["oop", "OOP", "class"])
    assert u.title == "Classes" and u.keywords == ["oop", "class"] and u.topic_id == "functions"
    moved = lib.update_resource(r.id, module_id="object-oriented-programming")
    assert moved.module_id == "object-oriented-programming"
    assert moved.topic_id is None
    assert moved.path.startswith("resources/object-oriented-programming/")
    assert not old_path.exists() and lib.file_path(moved).exists()
    t = lib.update_resource(r.id, topic_id="inheritance-and-polymorphism")
    assert t.topic_id == "inheritance-and-polymorphism"
    kept = lib.update_resource(r.id, description="d")
    assert kept.topic_id == "inheritance-and-polymorphism"
    cleared = lib.update_resource(r.id, topic_id=None)
    assert cleared.topic_id is None
    with pytest.raises(LibraryError):
        lib.update_resource("nope", title="x")


def test_replace_file(lib, make_file):
    r = lib.add_resource(make_file("v1.txt", "one"), "Doc", "python-fundamentals")
    old = lib.file_path(r)
    u = lib.update_resource(r.id, replace_file=make_file("v2.md", "two two"))
    assert u.filename == "v2.md" and u.size == 7 and not old.exists()
    assert lib.file_path(u).read_text(encoding="utf-8") == "two two"


def test_delete_resource(lib, make_file):
    r = lib.add_resource(make_file("gone.txt"), "Gone", "python-fundamentals")
    path = lib.file_path(r)
    lib.delete_resource(r.id)
    assert lib.resource(r.id) is None and not path.exists()
    assert lib.resources() == []
    lib.delete_resource(r.id)


def test_resources_filters_and_sorting(lib, make_file):
    a = lib.add_resource(make_file("b.txt", "x" * 50), "Bravo", "python-fundamentals", kind="exercise")
    b = lib.add_resource(make_file("a.txt", "x"), "alpha", "python-fundamentals", "functions", kind="notes")
    lib.add_resource(make_file("c.txt"), "Charlie", "databases-and-sql")
    assert [r.title for r in lib.resources(sort="title")] == ["alpha", "Bravo", "Charlie"]
    assert {r.id for r in lib.resources(module_id="python-fundamentals")} == {a.id, b.id}
    assert [r.id for r in lib.resources(module_id="python-fundamentals", topic_id="functions")] == [b.id]
    assert [r.id for r in lib.resources(kind="exercise")] == [a.id]
    assert lib.resources(sort="size")[0].id == a.id
    assert len(lib.recent(2)) == 2


def test_search_fields_and_content(lib, make_file):
    a = lib.add_resource(make_file("bio.txt", "Notes about photosynthesis in leaves."), "Plant notes",
                         "data-analysis", keywords=["biology"])
    b = lib.add_resource(make_file("loops.md", "# Loops\nUse a for loop."), "Iteration", "python-fundamentals",
                         "control-flow", description="Repeating code")
    assert [r.id for r in lib.search("photosynthesis")] == [a.id]
    assert [r.id for r in lib.search("photo")] == [a.id]
    assert [r.id for r in lib.search("biology")] == [a.id]
    assert [r.id for r in lib.search("control flow")] == [b.id]
    assert [r.id for r in lib.search("repeating")] == [b.id]
    assert lib.search("loop", module_id="data-analysis") == []
    assert lib.search("") == [] and lib.search("!!!") == []
    assert "photosynthesis" in lib.match_snippet(a.id, "photosynthesis")
    assert lib.content_text(a) == "Notes about photosynthesis in leaves."


def test_all_keywords_by_frequency(lib, make_file):
    lib.add_resource(make_file("1.txt"), "1", "python-fundamentals", keywords=["loops", "python"])
    lib.add_resource(make_file("2.txt"), "2", "python-fundamentals", keywords=["Python"])
    assert lib.all_keywords() == ["python", "loops"]


def test_copy_to_never_overwrites(lib, make_file, tmp_path):
    r = lib.add_resource(make_file("x.txt", "data"), "X", "python-fundamentals")
    dest = tmp_path / "downloads"
    first = lib.copy_to(r, dest)
    second = lib.copy_to(r, dest)
    assert first.name == "x.txt" and second.name == "x 2.txt"


def test_classwork_crud(lib, make_file):
    commits = []
    lib.commit_requested.connect(lambda m, p: commits.append(p))
    c = lib.add_classwork("python-fundamentals", "2026-10-01", " Loops lab ", "Practice", "control-flow",
                          "Ana", make_file("lab.pdf", b"%PDF-1.4"))
    assert c.title == "Loops lab" and c.attachment_name == "lab.pdf"
    assert c.attachment.startswith("classwork/python-fundamentals/2026-10-01")
    assert lib.attachment_path(c).exists() and c.attachment in commits[-1]
    assert lib.counts()["__classwork__"] == 1
    with pytest.raises(LibraryError):
        lib.add_classwork("python-fundamentals", "10/01/2026", "Bad date")
    with pytest.raises(LibraryError):
        lib.add_classwork("python-fundamentals", "2026-10-01", "  ")
    with pytest.raises(LibraryError):
        lib.add_classwork("nope", "2026-10-01", "x")

    old_att = lib.attachment_path(c)
    u = lib.update_classwork(c.id, title="Loops workshop", remove_attachment=True)
    assert u.title == "Loops workshop" and u.attachment is None and not old_att.exists()
    assert u.topic_id == "control-flow"
    m = lib.update_classwork(c.id, module_id="databases-and-sql")
    assert m.module_id == "databases-and-sql" and m.topic_id is None
    lib.add_classwork("python-fundamentals", "2026-09-01", "Older", "SQL joins")
    assert [e.date for e in lib.classwork()] == ["2026-10-01", "2026-09-01"]
    assert [e.id for e in lib.search_classwork("workshop")] == [c.id]
    assert [e.title for e in lib.search_classwork("joins")] == ["Older"]
    lib.delete_classwork(c.id)
    assert lib.classwork_entry(c.id) is None
    assert len(lib.classwork()) == 1


def test_syllabus_crud(lib):
    m = lib.add_module("Web Basics", "HTML and CSS", topics=["HTML", "CSS", "html"])
    assert m.id == "web-basics" and [t.name for t in m.topics] == ["HTML", "CSS"]
    with pytest.raises(LibraryError):
        lib.add_module("web basics")
    with pytest.raises(LibraryError):
        lib.add_module("  ")
    lib.update_module(m.id, name="Web Fundamentals", color="red")
    assert lib.module(m.id).name == "Web Fundamentals" and lib.module(m.id).color == "red"
    t = lib.add_topic(m.id, "JavaScript")
    assert t.id == "javascript"
    with pytest.raises(LibraryError):
        lib.add_topic(m.id, "javascript")
    lib.rename_topic(m.id, t.id, "JS")
    assert lib.topic_name(m.id, t.id) == "JS"
    lib.delete_topic(m.id, t.id)
    assert lib.module(m.id).topic(t.id) is None
    lib.move_module(m.id, 0)
    assert lib.modules()[0].id == m.id
    saved = json.loads(lib.syllabus_file.read_text(encoding="utf-8"))
    assert saved["modules"][0]["name"] == "Web Fundamentals"


def test_delete_topic_clears_resource_topic(lib, make_file):
    r = lib.add_resource(make_file("f.txt"), "F", "python-fundamentals", "functions")
    lib.delete_topic("python-fundamentals", "functions")
    assert lib.resource(r.id).topic_id is None


def test_delete_module_guard(lib, make_file):
    r = lib.add_resource(make_file("keep.txt"), "Keep", "software-testing")
    lib.add_classwork("software-testing", "2026-10-02", "Debug session")
    assert lib.module_usage("software-testing") == (1, 1)
    with pytest.raises(LibraryError) as info:
        lib.delete_module("software-testing")
    assert "1 resource" in str(info.value) and "1 classwork entry" in str(info.value)
    assert lib.module("software-testing") is not None
    path = lib.file_path(r)
    lib.delete_module("software-testing", delete_contents=True)
    assert lib.module("software-testing") is None
    assert lib.resource(r.id) is None and not path.exists() and lib.classwork(module_id="software-testing") == []
    empty = lib.add_module("Empty")
    lib.delete_module(empty.id)
    assert lib.module(empty.id) is None


def test_index_rebuilt_from_json_mirror(tmp_path, make_file):
    root = tmp_path / "lib"
    lib = Library(root)
    r = lib.add_resource(make_file("mirror.txt", "quantum entanglement"), "Mirror", "data-analysis",
                         keywords=["physics"])
    c = lib.add_classwork("data-analysis", "2026-10-03", "Charts")
    m = lib.add_module("Extra", topics=["One"])
    lib.close()
    shutil.rmtree(root / ".index")

    again = Library(root)
    try:
        assert not again.created
        assert again.resource(r.id).title == "Mirror"
        assert again.classwork_entry(c.id).title == "Charts"
        assert again.module(m.id).topics[0].name == "One"
        assert [x.id for x in again.search("entanglement")] == [r.id]
        assert [x.id for x in again.search("physics")] == [r.id]
    finally:
        again.close()


def test_reload_picks_up_external_json_changes(lib, make_file):
    events = []
    lib.changed.connect(events.append)
    r = lib.add_resource(make_file("ext.txt"), "Before", "python-fundamentals")
    data = json.loads(lib.resources_file.read_text(encoding="utf-8"))
    data["resources"][0]["title"] = "After"
    lib.resources_file.write_text(json.dumps(data), encoding="utf-8")
    lib.reload()
    assert lib.resource(r.id).title == "After" and events[-1] == "all"


def test_path_outside_library_rejected(lib):
    with pytest.raises(LibraryError):
        lib.abs("../outside.txt")


@pytest.mark.parametrize("text, expected", [
    ("Python Fundamentals", "python-fundamentals"),
    ("Variables & Data Types", "variables-and-data-types"),
    ("  Café Déjà Vu!  ", "cafe-deja-vu"),
    ("!!!", "item"),
])
def test_slugify(text, expected):
    assert slugify(text) == expected


def test_slugify_fallback_and_length():
    assert slugify("", "module") == "module"
    assert len(slugify("x" * 100)) <= 48


@pytest.mark.parametrize("name, expected", [
    ("notes.pdf", "notes.pdf"),
    ('a<b>:c"d/e\\f|g?h*.txt', "a_b__c_d_e_f_g_h_.txt"),
    ("CON.txt", "_CON.txt"),
    ("nul", "_nul"),
    ("  .hidden.  ", "hidden"),
    ("", "file"),
])
def test_safe_filename(name, expected):
    assert safe_filename(name) == expected


def test_safe_filename_truncates_keeping_extension():
    out = safe_filename("a" * 200 + ".docx")
    assert len(out) == 120 and out.endswith(".docx")


def test_normalize_keywords():
    assert normalize_keywords(["  Python ", "python", "#loops", "a,", "", "  multi   word "]) == \
        ["Python", "loops", "a", "multi word"]
    assert len(normalize_keywords(str(i) for i in range(50))) == 20
