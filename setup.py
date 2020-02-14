import pyroutelib3
from setuptools import setup

with open("README.md", "r", encoding="utf-8") as f:
    readme = f.read()

setup(
  name = "pyroutelib3",
  py_modules = ["pyroutelib3"],
  license = pyroutelib3.__license__,
  version = pyroutelib3.__version__,
  description = pyroutelib3.__description__,
  long_description = readme,
  long_description_content_type = "text/markdown",
  author = pyroutelib3.__url__,
  maintainer = pyroutelib3.__maintainer__,
  maintainer_email = pyroutelib3.__email__,
  url = pyroutelib3.__url__,
  keywords = "osm routing pyroutelib",
  classifiers = [],
  install_requires = ["osmiter"],
)
