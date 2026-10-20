# Runtime Source Materials

MEDIANOCHE's proprietary license does not apply to third-party runtime libraries
or their source. Original notices and license texts remain unchanged.

The prepared source-material archive is named
`THIRD-PARTY-SOURCES-0.1.0.tar.gz`. It contains original source archives, original
build recipes, upstream download URLs and SHA-256 inventory, with no MEDIANOCHE
game sources or assets.

Identified LGPL libraries are Windows mpg123 **1.25.6**, Windows OpenAL Soft
**1.19.1**, Linux OpenAL Soft **1.23.1**, and Linux mpg123 **1.31.3**.
Windows versions and Linux OpenAL are identified by embedded version/build-path
strings and official source/build records. Linux mpg123 correspondence is verified
by [CI source comparison](https://github.com/javieratomic/medianoche/actions/runs/39472377036):
the packaged 1.31.3 source and original recipe reproduce the shipped library's
`.text`, `.rodata` and GNU build ID. The archive includes the exact proof hashes.

Download the [runtime source archive](https://github.com/javieratomic/medianoche/releases/download/v0.1.0/THIRD-PARTY-SOURCES-0.1.0.tar.gz)
beside the binaries on the [same release page](https://github.com/javieratomic/medianoche/releases/tag/v0.1.0),
with equivalent access. Its SHA-256 is included in the release checksums.
The upstream libraries retain all permissions granted by their own
licenses, including modification and replacement as those licenses provide.
