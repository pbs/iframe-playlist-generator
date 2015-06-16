from setuptools import setup

setup(
    name='iframe-playlist-generator',
    version='0.1.3',
    author='Peter Norton',
    author_email='peter@nortoncrew.com',
    packages=['iframeplaylistgenerator'],
    url='https://github.com/pbs/iframe-playlist-generator',
    description='HLS I-frame playlist generator',
    long_description=open('README.rst').read(),
    install_requires=['m3u8==0.1.8', 'subprocess32==3.2.6'],
)
