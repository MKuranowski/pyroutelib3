from setuptools import setup

with open("README.md", "r", encoding="utf-8") as f:
    readme = f.read()

setup(
    name="pyroutelib3",
    py_modules=["pyroutelib3"],
    license="GPL v3",
    version="1.7.0-pre2",
    description="Library for simple routing on OSM data",
    long_description=readme,
    long_description_content_type="text/markdown",
    author="Oliver White",
    maintainer="Mikolaj Kuranowski",
    url="https://github.com/MKuranowski/pyroutelib3",
    keywords="osm routing pyroutelib",
    classifiers=[],
    python_requires=">=3.6, <4",
    install_requires=["osmiter>=1.1", "typing_extensions"],
)
