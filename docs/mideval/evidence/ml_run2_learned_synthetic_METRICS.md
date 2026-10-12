| layout | style | valid | free-space IoU | corridor IoU | room P | room R | label acc | door P | door R | scale err % | routes found | route/true | wall crossings | s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| basic | greyfill | True | 1.0 | 0.994 | 1.0 | 1.0 | 0.857 | 1.0 | 1.0 | -2.2 | 1.0 | 1.212 | 0 | 8.2 |
| basic | blackwalls | True | 1.0 | 0.994 | 1.0 | 1.0 | 0.571 | 1.0 | 1.0 | -2.2 | 1.0 | 1.212 | 0 | 2.6 |
| basic | thinlines | True | 0.931 | 0.266 | 0.25 | 0.143 | 1.0 | 0.0 | 0.0 | 87.5 | 0.0 | None | 10 | 3.0 |
| basic | doubleline | True | 0.926 | 0.141 | 0.545 | 0.857 | 0.5 | 0.556 | 0.833 | -48.9 | 0.0 | None | 0 | 2.5 |
| basic | colored | True | 1.0 | 0.994 | 1.0 | 1.0 | 0.714 | 1.0 | 1.0 | -2.2 | 1.0 | 1.212 | 0 | 2.8 |
| basic | scanned | True | 0.987 | 0.984 | 1.0 | 1.0 | 0.571 | 1.0 | 1.0 | -6.3 | 1.0 | 1.29 | 0 | 3.1 |
| lshape | greyfill | True | 0.889 | 0.994 | 0.692 | 1.0 | 0.889 | 1.0 | 1.0 | -2.2 | 1.0 | 1.267 | 0 | 4.1 |
| lshape | blackwalls | True | 0.868 | 0.994 | 0.75 | 1.0 | 0.333 | 0.889 | 1.0 | -2.2 | 1.0 | 1.267 | 0 | 4.1 |
| lshape | thinlines | True | 0.816 | 0.245 | 0.333 | 0.111 | 1.0 | 0.0 | 0.0 | 25.0 | 0.0 | None | 7 | 4.1 |
| lshape | doubleline | True | 0.908 | 0.134 | 0.5 | 0.889 | 0.625 | 0.615 | 1.0 | 2.3 | 0.0 | None | 0 | 3.7 |
| lshape | colored | True | 0.911 | 0.994 | 0.75 | 1.0 | 0.444 | 1.0 | 1.0 | -2.2 | 1.0 | 1.267 | 0 | 4.0 |
| lshape | scanned | True | 0.834 | 0.973 | 0.75 | 1.0 | 0.222 | 0.8 | 1.0 | -10.0 | 1.0 | 1.328 | 0 | 5.3 |
| **mean** | | 12/12 | 0.922 | 0.726 | 0.714 | 0.833 | 0.644 | 0.738 | 0.819 | 16.100 | 0.667 | 1.257 | 1.417 | |

segmenter: learned (run 2, checkpoint sha256 2a1c4277d65aba1b…); produced on Kaggle by `scripts/kaggle_train.sh` →
`python eval/evaluate_synthetic.py --segmenter learned --out /kaggle/working/out/eval_synth_learned`. Copied from the Kaggle
console output; the file itself is in the saved Kaggle notebook version's output (`out/eval_synth_learned/METRICS.md`).
