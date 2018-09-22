from setuptools import setup

with open("README.md", "r", encoding="utf-8") as f:
    readme = f.read()

setup(
  name = "pyroutelib3",
  py_modules = ["pyroutelib3"],
  license = "GPL v3",
  version = "1.2",
  description = "Library for simple routing on OSM data",
  long_description = readme,
  long_description_content_type = "text/markdown",
  author = "Oliver White",
  maintainer = "Mikolaj Kuranowski",
  maintainer_email = "mkuranowski@gmail.com",
  url = "https://github.com/MKuranowski/pyroutelib3",
  download_url = "https://github.com/MKuranowski/pyroutelib3/archive/1.2.tar.gz",
  keywords = "osm routing pyroutelib",
  classifiers = [],
  install_requires = ["osmapi", "python-dateutil"]
)
