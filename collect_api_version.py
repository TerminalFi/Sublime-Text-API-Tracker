#!/usr/bin/env python3

import ast
import json
import os
import time
import urllib.request
import zipfile
from urllib.parse import unquote

import github3

# ! Sublime Class
# ~ Classes that are part of the API in general; the source files contain some
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

# TODO - Better implementation
# - There has to be a better way
# - to implement this.
seen_previously = list()


class SublimeTextAPIVersion:
    def __init__(self):
        self.github = github3.login(token=os.environ["GITHUB_API_TOKEN"])
        self.repository = self.github.repository(
            "TheSecEng", "Sublime-Text-API-Tracker"
        )
        self.master = self.repository.commit("master")
        self.master_branch = "master"
        self.api_update_branch = "%s-%s" % (
            "api/update",
            str(round(time.time() * 1000)),
        )
        self.sublime_api_list_endpoint = "/sublime_api_list.json"
        self.sublime_version_list_endpoint = "/sublime_version_list.json"
        self.new_versions = 0
        self.results = dict()

    def run(self):
        self.sublime_api_list = self.repository.file_contents(
            self.sublime_api_list_endpoint
        )
        self._get_api_list(
            self.repository.file_contents(self.sublime_api_list_endpoint).decoded
        )
        self._get_version_list(
            self.repository.file_contents(self.sublime_version_list_endpoint).decoded
        )

        for version in self.sublime_version_list_content["data"]:
            if version["version"] in self.sublime_api_list_content.keys():
                print(f"Version List: {version} - Already Processed")
                continue

            self.new_versions += 1
            save_path = download_sublime(version["url"])
            self.results = handle_archive(version["version"], save_path, self.results)
            os.remove(save_path)

        if self.new_versions != 0:
            self.sublime_api_list_content.update(self.results)
            self._create_new_branch()
            self._push_commit_to_branch()
            self._create_pull_request()

    def _create_new_branch(self):
        self.repository.create_branch_ref(self.api_update_branch, self.master)

    def _push_commit_to_branch(self):
        self.sublime_api_list.update(
            "Updating API Documentation",
            json.dumps(self.sublime_api_list_content, indent=4).encode("utf-8"),
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

    def _get_api_list(self, encoded_list):
        global seen_previously
        decoded_list = encoded_list.decode("UTF-8")
        self.sublime_api_list_content = ast.literal_eval(decoded_list)
        for key in self.sublime_api_list_content:
            for item in self.sublime_api_list_content[key]:
                if key not in seen_previously:
                    seen_previously += [item]

    def _get_version_list(self, encoded_list):
        decoded_list = encoded_list.decode("UTF-8")
        self.sublime_version_list_content = ast.literal_eval(decoded_list)


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
    global seen_previously
    key = "%s.%s" % (module_name, obj_name)
    if method_name:
        key += ".%s" % method_name

    if build not in results:
        results[build] = []

    if key not in results[build] and key not in seen_previously:
        results[build] += [key]

    if key not in seen_previously:
        seen_previously += [key]


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
    with urllib.request.urlopen(url) as dl_file:
        with open(save_path, "wb") as out_file:
            out_file.write(dl_file.read())
    return save_path


if __name__ == "__main__":
    sublime_api_indexer = SublimeTextAPIVersion()
    sublime_api_indexer.run()
