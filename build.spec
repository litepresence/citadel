# -*- mode: python -*-
import version
EXE_NAME=version.UNIX_NAME

import os
import sys
import platform
def is_os_64bit():
    return platform.machine().endswith('64')


binaries = [ ]
hidden_imports = [ ]

def download_file(filename, url):
    if not(os.path.isfile(filename)):
        import requests
        print("Downloading", url)
        response = requests.get(url)
        try:
            html = response.text.startswith('<!DOCTYPE html>')
        except:
            html = False
        if html:
            raise Exception("Download error (some HTML is on the way)")
        with open(filename, "wb") as f:
            f.write(response.content)
    return filename
def extract_file(archive, name):
    import zipfile
    with zipfile.ZipFile(archive, "r") as zip:
        zip.extract(name)

def download_windows_openssl(i686=True):
    if i686:
        filename = 'openssl-1.0.2n-i386-win32.zip'
    else:
        filename = 'openssl-1.0.2n-x64_86-win64.zip'
    url = 'https://indy.fulgan.com/SSL/' + filename
    return download_file(filename, url)

if sys.platform == 'win32':
    EXE_NAME=version.BUNDLE_NAME

    i686 = not(is_os_64bit())
    archive = download_windows_openssl( i686 )
    #if i686:
    dlls = [ 'libeay32.dll', 'ssleay32.dll' ]
    for dll in dlls:
        extract_file(archive, dll)
    #    binaries.append( (dll, '.') )
    #else:
    #    pass
    import ntpath
    import imp
    dll = imp.find_module('_scrypt')[1]
    #binaries.append( (dll, '.') )
    #
    # NOTE: instead of adding to binaries, we just
    # provide "hidden_imports: _scrypt" below
    hidden_imports.append( '_scrypt' )

block_cipher = None

a = Analysis(['citadel'],
             pathex=[ ],
             binaries=binaries,
             datas=[],
             hiddenimports=hidden_imports,
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)

exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          name=EXE_NAME,
          debug=False,
          strip=False,
          upx=True,
          runtime_tmpdir=None,
          console=False,
          icon='images/app.ico')

#coll = COLLECT(exe,
#               a.binaries,
#               a.zipfiles,
#               a.datas,
#               strip=False,
#               upx=True,
#               name='main')
