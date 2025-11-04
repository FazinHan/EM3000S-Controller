from HolmarcMagnet import Controller

inst = Controller()
inst.connect()
inst.pulse(-2, 5)
inst.disconnect()