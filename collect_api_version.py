#!/usr/bin/env python3

import ast
import json
import os
import time
import zipfile
from collections import OrderedDict
from urllib import request
from urllib.parse import unquote

import github3

# ! Sublime Class
# * Classes that are part of the API in general; the source files contain some
# - helper classes that are just noise
_classes = [
    # ~ From the sublime module
    "Edit",
    "Phantom",
    "PhantomSet",
    "Region",
    "Selection",
    "Settings",
    "View",
    "Window",
    "Sheet",
    "HistoricPosition",
    "TextChange",
    "TextSheet",
    "ImageSheet",
    "HtmlSheet",
    "Html",
    "CompletionList",
    "CompletionItem",
    # ~ From the sublime_plugin module
    "ApplicationCommand",
    "EventListener",
    "ListInputHandler",
    "TextCommand",
    "TextInputHandler",
    "ViewEventListener",
    "WindowCommand",
    "BackInputHandler",
    # These are special base classes; we don't want to spit them out directly
    # but we do want to remember they exist because they provide the API to
    # their base classes. The members for event listeners comes from the
    # 'all_callbacks' dictionary at the top level of sublime_plugin.py
    # "Command", "CommandInputHandler",
]

sublime_api_files = {
    "sublime.py": True,
    "sublime_plugin.py": False,
    "Lib/python33/sublime.py": True,
    "Lib/python33/sublime_plugin.py": False,
    "Lib/python38/sublime.py": True,
    "Lib/python38/sublime_plugin.py": False,
}

api_endpoint = "/apis.json"
version_endpoint = "/versions.json"
diff_history_endpoint = "/diffs.json"


class DiffEngine:
    def __init__(self, original: list, new: list):
        self.original = original
        self.new = new
        self.changes = {}
        self.final = []

    def diff(self) -> (list, dict):
        original = self.original
        changes = {"added": [], "removed": []}
        new = self.new.copy()
        for item in self.new:
            if item in original:
                self.final.append(new.pop(new.index(item)))
                original.pop(original.index(item))
                continue
            new_item = new.pop(new.index(item))
            changes["added"].append(new_item)
            self.final.append(new_item)

        for item in original:
            if item not in new:
                changes["removed"].append(item)

        self.changes = changes
        return (self.final, self.changes)


class SublimeTextAPIVersion:
    def __init__(self):
        self.new_version = False
        self.new_versions = 0
        self.results = {}
        self.github = github3.login(token=os.environ["GITHUB_API_TOKEN"])
        self.repository = self.github.repository(
            "TheSecEng", "Sublime-Text-API-Tracker"
        )
        self.master = self.repository.commit("v2/re-write")
        self.master_branch = "v2/re-write"
        self.api_update_branch = "%s-%s" % (
            "api/update",
            str(round(time.time() * 1000)),
        )

    def run(self):
        self.pull_requests = [
            i.head.ref for i in self.repository.pull_requests(state="open")
        ]
        self.sublime_api_list = self.repository.file_contents(
            api_endpoint, self.master_branch
        )
        self.sublime_version_list = self.repository.file_contents(
            version_endpoint, self.master_branch
        )
        self.sublime_diffs_list = self.repository.file_contents(
            diff_history_endpoint, self.master_branch
        )
        self._get_api_list()
        self._get_version_list()
        self._get_diff_list()

        for version in sorted(self.version_download_url.keys()):
            if version in self.diffs_content.keys():
                continue

            self.new_versions += 1
            save_path = download_sublime(self.version_download_url[version])
            self.results = handle_archive(version, save_path, self.results)
            os.remove(save_path)
            de = DiffEngine(self.sublime_api_list_content, self.results[version])
            api_list, diff = de.diff()
            self.diffs_content[version] = diff
            self.sublime_api_list_content = api_list

        if self.new_versions != 0:
            latest = sorted(self.version_download_url.keys())[-1]
            self.api_update_branch = "%s_%s" % ("api/update", latest,)

        if self.api_update_branch not in self.pull_requests:
            self._create_new_branch()
            self._push_commit_to_branch()
            self._create_pull_request()

    def _create_new_branch(self):
        try:
            self.repository.create_branch_ref(self.api_update_branch, self.master)
        except github3.GitHubError as error:
            print(error.errors)

    def _push_commit_to_branch(self):
        self.sublime_api_list.update(
            "Updating API Documentation",
            json.dumps(self.sublime_api_list_content, indent=4).encode("utf-8"),
            branch=self.api_update_branch,
        )
        self.sublime_diffs_list.update(
            "Updating API Documentation",
            json.dumps(self.diffs_content, indent=4).encode("utf-8"),
            branch=self.api_update_branch,
        )

    def _create_pull_request(self):
        message = f"## Sublime API Documentation Update\n\n**New Versions Added:** _{self.new_versions}_"
        self.repository.create_pull(
            "[API] - Updating Sublime Text API Doc's",
            self.master_branch,
            "TheSecEng:%s" % self.api_update_branch,
            message,
        )

    def _get_api_list(self):
        self.sublime_api_list_content = ast.literal_eval(
            self.sublime_api_list.decoded.decode("UTF-8")
        )

    def _get_version_list(self):
        self.version_download_url = OrderedDict(
            ast.literal_eval(self.sublime_version_list.decoded.decode("UTF-8"))
        )

    def _get_diff_list(self):
        self.diffs_content = OrderedDict(
            ast.literal_eval(self.sublime_diffs_list.decoded.decode("UTF-8"))
        )


def _get_class_methods(cls_node, base=None):
    """
    Return a sorted list of the methods in a given class node. The methods in
    the base list (if any) are also included. Private methods are excluded and
    the list is sorted lexically.
    """

    def keep(method):
        n = method.name
        if n.startswith("__"):
            return True
        return not (n.startswith("_") or n.endswith("_"))

    methods = list(base or [])
    for node in ast.iter_child_nodes(cls_node):
        if isinstance(node, ast.FunctionDef) and keep(node):
            methods.append(node.name)

    return sorted(methods)


def get_plugin_specials(module):
    """
    Capture the methods for special classes that are not fully defined in the
    module files themselves. This returns empty lists if invoked from a file
    that doesn't contain the appropriate classes.
    """
    cmd_methods = []
    input_methods = []
    events = []
    for node in ast.iter_child_nodes(module):
        # Pick up command class and input handler methods; these classes are
        # not directly exposed in the API (except to use as base classes) but
        # subclasses inherit them.
        if isinstance(node, ast.ClassDef):
            if node.name == "Command":
                cmd_methods = _get_class_methods(node)
            elif node.name == "CommandInputHandler":
                input_methods = _get_class_methods(node)

        # Find event handlers by getting the keys from the global all_callbacks
        # variable. NOTE: Not all of these apply to ViewEventListener (e.g.
        # on_new) so external work is needed to cull those after the fact.
        #
        # NOTE: Starting in the 4xxx build series, there is now a global
        # view_event_listener_excluded_callbacks set that indicates the events
        # excluded in view event listeners. However that doesn't help if you're
        # running this over the 3xxx series too, since that doesn't include
        # this and they end up showing up in that version anyway.
        elif isinstance(node, ast.Assign):
            for target in [n for n in node.targets if isinstance(n, ast.Name)]:
                if target.id == "all_callbacks":
                    events = [key.s for key in node.value.keys]

    return cmd_methods, input_methods, events


def add_result(results, build, module_name, obj_name, method_name=None):
    key = "%s.%s" % (module_name, obj_name)
    if method_name:
        key += ".%s" % method_name

    results.setdefault(build, [])
    if key not in results[build]:
        results[build].append(key)


def module_report(build, results, module, name, inc_funcs, inc_class):
    """
    Display a report containing the functions and/or classes in the given
    module. Parameters indicate if module level functions and/or classes should
    be extracted for the report.
    """
    cmd_methods, input_methods, events = get_plugin_specials(module)

    def base_methods(cls_name):
        """
        Get the methods from known base classes
        """
        if cls_name.endswith("Command"):
            return cmd_methods
        elif cls_name.endswith("InputHandler"):
            return input_methods
        elif cls_name.endswith("EventListener"):
            return events

        return []

    for node in ast.iter_child_nodes(module):
        # Capture functions
        if isinstance(node, ast.FunctionDef) and inc_funcs:
            add_result(results, build, name, node.name)

        # Capture classes
        elif isinstance(node, ast.ClassDef) and inc_class:
            if node.name in _classes:
                methods = _get_class_methods(node, base_methods(node.name))
                for method in methods:
                    add_result(results, build, name, node.name, method)


def load_module(build, results, handle, filename, inc_funcs=True, inc_class=True):
    """
    Given an open handle to the named file, load the file into an AST tree and
    generate a report of the contents, including functions or classes as
    requested.
    """
    module_name = os.path.splitext(os.path.basename(filename))[0]
    tree = ast.parse(handle.read(), filename)
    module_report(build, results, tree, module_name, inc_funcs, inc_class)


def handle_raw_file(build, filename, inc_funcs=True, inc_class=True):
    """
    Handle a single input file by loading it, parsing it into an AST, and then
    dumping the module it contains out.
    """
    with open(filename) as handle:
        load_module(build, handle, filename, inc_funcs, inc_class)


def process_archive_member(
    build, results, zipFile, entry, inc_funcs=True, inc_class=True
):
    try:
        load_module(build, results, zipFile.open(entry), entry, inc_funcs, inc_class)
    except KeyError:
        pass


def handle_archive(build, archive_name, results=None):
    """
    Handle both of the appropriate files from the given zip file version of a
    portable install of Sublime Text.
    """
    results = results or dict()

    with zipfile.ZipFile(archive_name, "r") as zFile:
        for key, value in sublime_api_files.items():
            process_archive_member(build, results, zFile, key, inc_funcs=value)
    return results


def download_sublime(url):
    save_path = "./%s" % unquote(url).split("/")[-1]
    with request.urlopen(url) as dl_file:
        with open(save_path, "wb") as out_file:
            out_file.write(dl_file.read())
    return save_path


if __name__ == "__main__":
    sublime_api_indexer = SublimeTextAPIVersion()
    sublime_api_indexer.run()
