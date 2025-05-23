<p align="center">
  <a href="https://xkcd.com/1128/">
    <img src="https://imgs.xkcd.com/comics/fifty_shades.png">
  </a>
</p>


# /rk9/

## Features

- Subscribe to e621 tags, receive DMs when matching posts are uploaded

## Running

### Docker

* Clone or download a copy of the repo
* Put your bot's Discord token in `docker-compose.yml`
* Run `docker compose up -d`

### uv

* Install [uv](https://docs.astral.sh/uv/getting-started/installation/)
* Clone or download a copy of the repo
* Create an `.env` file next to `main.py` containing your configuration (per `docker-compose.yml`)
* Additionally define the variable `RK9_DATA_DIR`, the directory rk9 will store data in.
* Run `uv run main.py`