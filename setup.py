from setuptools import setup

setup(
    name='iframe-playlist-generator',
    version='0.1.0',
    author='Peter Norton',
    author_email='peter@nortoncrew.com',
    packages=['iframeplaylistgenerator'],
    url='https://github.com/pbs/iframe-playlist-generator',
    description='HLS I-frame playlist generator',
    long_description=open('README.rst').read(),
    install_requires=['m3u8==0.1.8b'],
    dependency_links=['https://github.com/peter-norton/m3u8/tarball/master#egg=m3u8-0.1.8b'],
)
