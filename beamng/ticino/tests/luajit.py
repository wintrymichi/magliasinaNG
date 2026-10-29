"""Run a Lua file under LuaJIT without a luajit binary (the cloud container has none): pip install lupa.

    python tests/luajit.py <file.lua> [args...]
"""
import sys

from lupa import luajit21

rt = luajit21.LuaRuntime()
arg = rt.table(*sys.argv[2:])
arg[0] = sys.argv[1]
rt.globals().arg = arg
rt.execute(open(sys.argv[1]).read())
