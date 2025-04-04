# Incorporating Alternative Data into your Portfolio Rebalancing

This project is a collaboration between [Atoti Community](https://www.atoti.io) and [CloudQuant](https://www.cloudquant.com/).  


<center><img src="https://data.atoti.io/notebooks/banners/AtotiCommunity.png" alt="Atoti Community" style="height: 100px;" hspace="50"></a></div><img src="https://data.atoti.io/notebooks/alt-data/img/CloudQuantPNGLogo.png" alt="CloudQuant" style="height: 100px;" hspace="50"></a></div></center>


It's no secret that access to the right data along with the right aggregation engine allows Quants and portfolio managers to achieve their goals. The problem? How do you find good data, and what is the right aggregation tool?  

Discover how seamless it can be to incorporate alternative data into your rebalancing act. With CloudQuant’s datasets and Atoti Python SDK, we show you how to keep alternative data in mind when working through monthly portfolio rebalancing.

We demonstrate how, using [Atoti Python SDK](https://docs.atoti.io/) and [CloudQuant's Liberator API](https://www.cloudquant.com/data-liberator/), we can incorporate alternative data in our portfolio rebalancing. Specifically, we demonstrate how to:

1. Create a portfolio using Alphaflow
2. Compute returns using DailyBars in Atoti
3. Rebalance it monthly using Alphaflow long term signals
4. Subject to several ESG related constraints using ESG data
5. Compare across your portfolio options

This project is split across two notebooks:

1. [01_data_gen.ipynb](./01_data_gen.ipynb) demonstrates how we utilize CloudQuant's Liberator API to collect our data.  
2. [main.ipynb](./main.ipynb) to see how we pull it together with Atoti