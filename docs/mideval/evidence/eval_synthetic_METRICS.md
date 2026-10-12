| layout | style | valid | free-space IoU | corridor IoU | room P | room R | label acc | door P | door R | scale err % | routes found | route/true | wall crossings | s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| basic | greyfill | True | 1.0 | 0.994 | 1.0 | 1.0 | 0.857 | 1.0 | 1.0 | -2.2 | 1.0 | 1.212 | 0 | 2.0 |
| basic | blackwalls | True | 1.0 | 0.994 | 1.0 | 1.0 | 0.857 | 1.0 | 1.0 | -2.2 | 1.0 | 1.212 | 0 | 2.2 |
| basic | thinlines | True | 0.983 | 0.978 | 1.0 | 1.0 | 0.429 | 1.0 | 1.0 | -16.9 | 1.0 | 1.245 | 0 | 2.0 |
| basic | doubleline | True | 0.917 | 0.902 | 1.0 | 1.0 | 0.429 | 1.0 | 1.0 | 25.0 | 1.0 | 1.205 | 0 | 2.3 |
| basic | colored | True | 1.0 | 0.994 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | -2.2 | 1.0 | 1.212 | 0 | 2.1 |
| basic | scanned | True | 0.992 | 0.99 | 1.0 | 1.0 | 0.857 | 0.857 | 1.0 | -6.3 | 1.0 | 1.26 | 0 | 3.9 |
| lshape | greyfill | True | 1.0 | 0.994 | 1.0 | 1.0 | 0.889 | 1.0 | 1.0 | -2.2 | 1.0 | 1.267 | 0 | 2.8 |
| lshape | blackwalls | True | 1.0 | 0.994 | 1.0 | 1.0 | 0.667 | 1.0 | 1.0 | -2.2 | 1.0 | 1.265 | 0 | 2.7 |
| lshape | thinlines | True | 0.985 | 0.981 | 1.0 | 1.0 | 0.556 | 1.0 | 1.0 | -10.0 | 1.0 | 1.265 | 0 | 2.5 |
| lshape | doubleline | True | 0.924 | 0.905 | 1.0 | 1.0 | 0.444 | 1.0 | 1.0 | 28.6 | 1.0 | 1.262 | 0 | 3.2 |
| lshape | colored | True | 1.0 | 0.995 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | -2.2 | 1.0 | 1.267 | 0 | 2.8 |
| lshape | scanned | True | 0.993 | 0.991 | 1.0 | 1.0 | 0.444 | 1.0 | 1.0 | -4.3 | 1.0 | 1.266 | 0 | 5.2 |
| **mean** | | 12/12 | 0.983 | 0.976 | 1.000 | 1.000 | 0.702 | 0.988 | 1.000 | 8.692 | 1.000 | 1.245 | 0.000 | |

segmenter: classical; command: `python eval/evaluate_synthetic.py --out runs/eval_synth`
