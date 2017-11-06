from setuptools import setup

with open("README.md", "r", encoding="utf-8") as f:
    readme = f.read()

setup(
  name = "pyroutelib3",
  packages = ["pyroutelib3"],
  license = "GPL v3",
  version = "0.7",
  description = "Library for simple routing on OSM data",
  long_description = readme,
  author = "Oliver White",
  maintainer = "Mikolaj Kuranowski",
  maintainer_email = "mkuranowski@gmail.com",
  url = "https://github.com/MKuranowski/pyroutelib3",
  download_url = "https://github.com/MKuranowski/pyroutelib3/archive/0.7.tar.gz",
  keywords = "osm routing pyroutelib",
  classifiers = [],
  install_requires = ["osmapi"]
)
