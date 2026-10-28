# Third-party notices

## Original application source

A project-wide license for the original Movement Lens code has not been selected.
The dependency and media notices below do not assign one to this repository.

## Dependencies and optional preparation tools

The application declares FastAPI, Uvicorn, python-multipart, NumPy, scikit-learn,
threadpoolctl, React and Lucide. Optional integrations use Azure Identity, Azure
Blob Storage and the Microsoft Foundry/OpenAI Python clients. These components
retain their respective upstream licenses; consult the versions installed in
your environment.

- [FastAPI](https://github.com/fastapi/fastapi)
- [NumPy](https://github.com/numpy/numpy)
- [scikit-learn](https://github.com/scikit-learn/scikit-learn)
- [React](https://github.com/facebook/react)
- [Lucide](https://github.com/lucide-icons/lucide)
- [Azure SDK for Python](https://github.com/Azure/azure-sdk-for-python)
- [OpenAI Python client](https://github.com/openai/openai-python)

FFmpeg is a separately installed system tool. Optional source-bound pose
preparation uses separately installed OpenCV and Ultralytics and an existing
model checkpoint; these are not required for analysing compatible imported
windows. No model weights or third-party package source are bundled here.
[Touchline's notices](https://github.com/cweim/touchline/blob/main/THIRD_PARTY_NOTICES.md)
describe the upstream detector, tracker and appearance-model dependencies.

## Research and media

The app links to primary research and includes compact summaries with study
limitations. It does not redistribute the papers or treat those studies as
validation of the pose clusters.

Repository screenshots and the shared pipeline illustration are documented in
[media notes](docs/media/CREDITS.md). Football broadcast imagery remains
third-party material. Source videos, populated datasets, checkpoints and private
runtime records are excluded from this source repository.
