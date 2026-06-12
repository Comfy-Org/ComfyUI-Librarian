# ComfyUI-Librarian

ComfyUI-Librarian is a ComfyUI custom node pack that caches model files when
ComfyUI loads them. It monkey-patches `comfy.utils.load_torch_file`, so no
workflow nodes are added.

The intended use is a fast cache drive in front of a slower model library. On a
cache miss, Librarian copies the model into the cache and then lets ComfyUI load
the cached copy.

## Configuration

Restart ComfyUI after installing, then open:

```text
Librarian -> Configure
```

Settings are saved immediately.

- **Enable cache**: enables or disables cache use. Defaults to enabled.
- **Cache parent directory**: parent folder where `.comfyUI-Librarian` will be
  created. No default is assumed; choose a writable folder on a faster drive.
- **Max Cache Size**: maximum cache payload size in GB.
- **Disable Startup Check**: suppresses the startup configuration popup.

If no cache directory is configured, Librarian leaves model loads untouched.

## Cache layout

Cached files are stored under:

```text
<cache parent>/.comfyUI-Librarian/
```

Files are addressed by a hash with two-character fanout directories:

```text
.comfyUI-Librarian/ab/cdef...--original_filename.safetensors
```

The hash includes:

- original basename
- file creation/change timestamp
- safetensors header hash, for `.safetensors` and `.sft` files

Only the original basename is kept for human inspection. The original directory
is not stored in the cached filename.

## LRU and quota

Librarian uses file access times as its persistent LRU state. Cache hits touch
the cached file with `os.utime`, and pruning removes the least-recently-used
cached files first.

Before copying, Librarian enforces both:

- configured max cache size
- 32GB free-space headroom on the cache filesystem

If either limit cannot be satisfied, the original model path is used.

## Same-filesystem skip

If the source model and cache root resolve to the same filesystem, Librarian
skips caching. This uses `realpath` before comparing filesystem device IDs, so
symlinks and junction-like paths are accounted for.

The skip is logged once per model identity, then recorded under:

```text
.comfyUI-Librarian/.markers/
```

## Console output

On cache miss, Librarian logs:

```text
[INFO] ComfyUI-Librarian: Cache miss on <file-basename>. populating cache
```

The copy then shows a `tqdm` progress bar prefixed only by the filename, with
percentage and transfer rate.

## Directory picker

The Browse button asks the ComfyUI Python process to open a native folder picker:

- Windows: PowerShell `System.Windows.Forms.FolderBrowserDialog`, rooted at
  `This PC`
- macOS: `osascript` folder picker
- Linux: `zenity`, then `kdialog`

If no picker is available or the dialog is cancelled, the cache directory is not
changed.
