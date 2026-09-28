---
license: odc-by
language:
- en
---

![image](https://cdn-uploads.huggingface.co/production/uploads/62608fc2ffe8827cb1d89f9f/XMW9_q0GCubxzTOgdsb4K.png)
<p align="center">
  💻 <a href="https://github.com/hamishivi/tmax">Code</a> ·
  🤗 <a href="https://huggingface.co/collections/allenai/tmax">Models &amp; Data</a> ·
  📜 <a href="https://arxiv.org/abs/2606.23321">Paper</a> ·
  📓 <a href="https://wai-org.com/blog/tmax/">Blog</a>
</p>

> [!NOTE]
> For full information, go check out the Tmax paper [here](https://arxiv.org/abs/2606.23321).

# TMax 15k - Open Instruct

This is the dataset we used to train [Tmax 9b](https://huggingface.co/allenai/tmax-9b) (and our other tmax models).
This release contains general details on the data.
In general, this is a collection of roughly 15k RL environment instances.
For details on how we generated this dataset and its makeup, please see our paper!

**You can find a version of this dataset ready for training [here](https://huggingface.co/datasets/allenai/tmax-15k-open-instruct)!**

## License

This dataset is licensed under ODC-BY.
It is intended for research and educational use in accordance with Ai2's [Responsible Use Guidelines](https://allenai.org/responsible-use).
The data includes outputs generated using Gemini 3.1 Pro, which are subject to Google's [Terms of Service](https://policies.google.com/terms). 

## Citation

If you use our model or data, please cite our paper:
```
@misc{ivison2026tmaxsimplerecipeterminal,
      title={Tmax: A simple recipe for terminal agents}, 
      author={Hamish Ivison and Junjie Oscar Yin and Rulin Shao and Teng Xiao and Nathan Lambert and Hannaneh Hajishirzi},
      year={2026},
      eprint={2606.23321},
      archivePrefix={arXiv},
      primaryClass={cs.CL},
      url={https://arxiv.org/abs/2606.23321}, 
}
```