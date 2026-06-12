# ComfyUI-Librarian

ComfyUI-Librarian is a ComfyUI extension that caches model files when
ComfyUI loads them.

Use this if you have your model library on a big slow drive but have a smaller
faster drive available to keep recently used models.

Use for spinning HDD, external drive or network storage paired with a local
NVME or fast SSD.

Models will remain cached on the fast disk until the cache storage is
exhausted. Models remain cached even through a comfyUI restart.

## Installation

Clone into you `custom_nodes` folder:

```
git clone https://github.com/rattus128/ComfyUI-Librarian ComfyUI/custom_nodes/ComfyUI-Librarian
```

Restart ComfyUI and refresh your comfy browser tab if already running.

## Usage

On first usage the configuration will popup. Navigate to your fast
drive with "browse" and set the amount of storage to budget for the cache.
256GB is a good size. Smaller is ok if running workflows repeatedly.
Larger is better if jumping around lots of models.

Then use ComfyUI normally. No extra nodes needed. (this is integrated
with the standard native file loader).
