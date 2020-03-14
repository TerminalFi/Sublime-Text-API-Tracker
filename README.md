# Sublime Text API Version Documenter
### Inspired by [ODatNurd](https://github.com/OdatNurd)
_**ODatNurd**_ provided the logic and core script for grabbing API information from **Sublime Texts** python files. As well as the initial idea and motivation for providing this type of documentation.


## Description
This tool is meant to provide a fast and easy way for _Sublime Text_ api's to be mapped to the version they were initially supported it. As new versions of Sublime Text are released, the `sublime_version_list.json` needs to be updated. Once a PR is merged updating that file, a Github Action will trigger to fetch the newest API information and generate a PR to merge into master.


## Contributing
1. Fork the repo
2. Update `sublime_version_list.json` with the new version number and url to the Windows x64 portable edition
3. Submit a PR
4. Enjoy!