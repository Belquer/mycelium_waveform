# examples/

Drop your `.wav` files here to keep them next to the project.

The `.gitignore` keeps WAVs out of the repo by default — only
`multitudes_sample.wav` is tracked (if you choose to commit it).

To run a quick headless test against a WAV in this folder:

```bash
python main.py --cli examples/your_voice.wav out/ --profile FDM_PLASTIC
```
