from pyteal import *


class OptIn:
    group = And(
        # Check Txn
        Txn.type_enum() == TxnType.ApplicationCall,
        Txn.assets[0] == App.globalGet(Bytes("token")),
        Txn.fee() == Int(2) * Global.min_txn_fee()
    )
    optin = Seq(
        Assert(group),
        # If admin, send large amount of tokens to admin
        If(
            App.globalGet(Bytes("admin")) == Txn.sender()
        ).Then(
            Seq(
                InnerTxnBuilder.Begin(),
                InnerTxnBuilder.SetFields({
                    TxnField.type_enum: TxnType.AssetTransfer,
                    TxnField.xfer_asset: Txn.assets[0],
                    TxnField.asset_receiver: Txn.accounts[0],
                    TxnField.asset_amount: Int(10_000_000_000_000),
                }),
                InnerTxnBuilder.Submit(),
                # Set last updated flag
                App.localPut(Txn.sender(), Bytes("last_updated"), Global.latest_timestamp() / Int(60*60)),
            )
        ).Else(
            Seq(
                InnerTxnBuilder.Begin(),
                InnerTxnBuilder.SetFields({
                    TxnField.type_enum: TxnType.AssetTransfer,
                    TxnField.xfer_asset: Txn.assets[0],
                    TxnField.asset_receiver: Txn.accounts[0],
                    TxnField.asset_amount: Int(1_000_000_000),
                }),
                InnerTxnBuilder.Submit(),
                # Set last updated flag
                App.localPut(Txn.sender(), Bytes("last_updated"), Global.latest_timestamp() / Int(60*60)),
            )
        ),
        Approve()
    )


class Boot:
    group = And(
        # Ensure contract has not been booted already
        App.globalGet(Bytes("boot")),
        # Seed the contract account with Algo
        Gtxn[0].type_enum() == TxnType.Payment,
        # How much algo must be sent to the contract account on boot
        Gtxn[0].amount() == Int(300_000),
        Gtxn[0].sender() == Txn.sender(),
        Gtxn[0].receiver() == Global.current_application_address(),
        # Check Txn
        Txn.group_index() == Int(1),
        Txn.type_enum() == TxnType.ApplicationCall,
        Txn.sender() == App.globalGet(Bytes("admin")),
        Txn.fee() == Int(2) * Global.min_txn_fee()
    )
    noop = Seq(
        Assert(group),
        If(
            App.globalGet(Bytes("admin")) == Txn.sender()
        ).Then(
            Seq(
                # Create Faucet tokens
                InnerTxnBuilder.Begin(),
                InnerTxnBuilder.SetFields({
                    TxnField.type_enum: TxnType.AssetConfig,
                    TxnField.config_asset_total: Int(18_000_000_000_000_000_000),
                    TxnField.config_asset_decimals: Int(6),
                    TxnField.config_asset_unit_name: Bytes("TNR"),
                    TxnField.config_asset_name: Bytes("Testnet Rewards"),
                    TxnField.config_asset_url: Bytes("https://deridex.org"),
                    TxnField.config_asset_manager: Global.current_application_address(),
                    TxnField.config_asset_reserve: Global.current_application_address(),
                }),
                InnerTxnBuilder.Submit(),
                App.globalPut(Bytes("token"), InnerTxn.created_asset_id()),
                # Disable boot action
                App.globalPut(Bytes("boot"), Int(0)),
                Approve()
            )
        ).Else(
            Reject()
        )
    )


class Faucet:
    group = And(
        Txn.type_enum() == TxnType.ApplicationCall,
        Txn.assets[0] == App.globalGet(Bytes("token")),
        Txn.fee() == Int(2) * Global.min_txn_fee()
    )
    noop = Seq(
        Assert(group),
        # If it has been longer than an hour
        If(
            App.localGet(Txn.sender(), Bytes("last_updated")) < Global.latest_timestamp() / Int(60*60)
        ).Then(
            Seq(
                InnerTxnBuilder.Begin(),
                InnerTxnBuilder.SetFields({
                    TxnField.type_enum: TxnType.AssetTransfer,
                    TxnField.xfer_asset: Txn.assets[0],
                    TxnField.asset_receiver: Txn.accounts[0],
                    TxnField.asset_amount: Int(1_000_000_000),
                }),
                InnerTxnBuilder.Submit(),
                # Set last updated flag
                App.localPut(Txn.sender(), Bytes("last_updated"), Global.latest_timestamp() / Int(60*60)),
                Approve()
            )
        ).Else(
            Reject()
        ),
    )


def approval():
    # Handle tx types
    creation = Seq(
        # Admin address
        App.globalPut(Bytes("admin"), Txn.sender()),
        App.globalPut(Bytes("boot"), Int(1)),
        Approve()
    )

    optin = OptIn.optin

    closeout = Reject()

    update = Seq(
        If(
            App.globalGet(Bytes("admin")) == Txn.sender()
        ).Then(
            Approve()
        ).Else(
            Reject()
        )
    )

    delete = Reject()

    noop = Cond(
        # User Pool
        [Txn.application_args[0] == Bytes("faucet"), Faucet.noop],
        # Admin
        [Txn.application_args[0] == Bytes("boot"), Boot.noop],
    )

    program = Cond(
        [Txn.application_id() == Int(0), creation],
        [Txn.on_completion() == OnComplete.OptIn, optin],
        [Txn.on_completion() == OnComplete.CloseOut, closeout],
        [Txn.on_completion() == OnComplete.UpdateApplication, update],
        [Txn.on_completion() == OnComplete.DeleteApplication, delete],
        [Txn.on_completion() == OnComplete.NoOp, noop]
    )
    return program


def clear():
    return Return(Int(1))


if __name__ == "__main__":
    print(compileTeal(approval(), mode=Mode.Application, version=6))