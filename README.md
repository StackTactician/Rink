# Rink

Browse thenkiri.com and download movies, series and dramas - from a browser on
your own machine or from a terminal.

## Browser

```
python3 -m nkiri.web
```

Open `http://localhost:8321`, or that address with this machine's IP from a
phone on the same network. Search, open a title, pick a file, download.

## Terminal

```
python3 -m nkiri search "resident evil"
python3 -m nkiri list
python3 -m nkiri show 143755
python3 -m nkiri download 143755
```

`143755` stands for any post id or full thenkiri.com link.

## Notes

A personal tool, published as-is. No accounts, nothing stored beyond the
running process. It reads a site it does not own, so it works for as long as
that site does.
