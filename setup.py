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
    maintainer_email="".join(chr(i) for i in [109, 107, 117, 114, 97, 110, 111, 119, 115, 107, 105,
                                              64, 103, 109, 97, 105, 108, 46, 99, 111, 109]),
    url="https://github.com/MKuranowski/pyroutelib3",
    keywords="osm routing pyroutelib",
    classifiers=[],
    python_requires=">=3.6, <4",
    install_requires=["osmiter>=1.1", "typing_extensions"],
)
