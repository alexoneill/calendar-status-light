# app.py
# 2019-06-15

from flask import Flask


def main():
  app = Flask(__name__)

  @app.route('/')
  def root():
      return '200'

  app.run('0.0.0.0', 80)


if __name__ == '__main__':
  import sys
  main(*sys.argv[1:])
